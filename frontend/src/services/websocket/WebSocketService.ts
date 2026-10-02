import type {
  ClientMessageType,
  ServerMessageType,
  WsMessage,
  WsPayloadMap,
} from '@snapland/shared-types';
import {
  IWebSocketService,
  ConnectionState,
  MessageHandler,
} from '../../api/interfaces/IWebSocketService';
import { showToast } from '../../utils/toastService';
import { mapServerAreaToArea } from '../../api/http/client';

const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000];

type GenericHandler = (payload: unknown, eventId?: string) => void;

export class RealWebSocketService implements IWebSocketService {
  private socket: WebSocket | null = null;
  private state: ConnectionState = 'disconnected';
  private _lastEventId: string | null = null;
  private ticketProvider: (() => Promise<string>) | null = null;

  private handlers = new Map<ServerMessageType, Set<GenericHandler>>();
  private stateChangeHandlers = new Set<(state: ConnectionState) => void>();
  private resyncHandlers = new Set<() => void>();

  private consecutiveFailures = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalDisconnect = false;

  get connectionState(): ConnectionState {
    return this.state;
  }

  get lastEventId(): string | null {
    return this._lastEventId;
  }

  connect(ticketProvider: () => Promise<string>): void {
    this.ticketProvider = ticketProvider;
    this.intentionalDisconnect = false;

    if (this.state === 'connected' || this.state === 'connecting') {
      return;
    }

    this.initiateConnection();
  }

  disconnect(): void {
    this.intentionalDisconnect = true;
    this.clearReconnectTimer();

    if (this.socket) {
      // Normal closure
      this.socket.close(1000, 'Intentional disconnect');
      this.socket = null;
    }

    this.consecutiveFailures = 0;
    this.updateState('disconnected');
  }

  send<T extends ClientMessageType>(message: WsMessage<T>): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  on<T extends ServerMessageType>(
    type: T,
    handler: MessageHandler<T>
  ): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    const set = this.handlers.get(type)!;
    const castedHandler = handler as GenericHandler;
    set.add(castedHandler);

    return () => {
      set.delete(castedHandler);
    };
  }

  onStateChange(handler: (state: ConnectionState) => void): () => void {
    this.stateChangeHandlers.add(handler);
    handler(this.state);
    return () => {
      this.stateChangeHandlers.delete(handler);
    };
  }

  onResync(handler: () => void): () => void {
    this.resyncHandlers.add(handler);
    return () => {
      this.resyncHandlers.delete(handler);
    };
  }

  private updateState(newState: ConnectionState): void {
    if (this.state === newState) return;
    this.state = newState;
    this.stateChangeHandlers.forEach((handler) => {
      try {
        handler(newState);
      } catch (err) {
        console.error('Error in onStateChange handler', err);
      }
    });
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private getWebSocketUrl(ticket: string): string {
    const customWsUrl = import.meta.env.VITE_WS_URL;
    let url: string;

    if (customWsUrl) {
      url = `${customWsUrl}?ticket=${encodeURIComponent(ticket)}`;
    } else if (typeof window !== 'undefined') {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      url = `${protocol}//${window.location.host}/ws?ticket=${encodeURIComponent(ticket)}`;
    } else {
      url = `ws://localhost:8000/ws?ticket=${encodeURIComponent(ticket)}`;
    }

    if (this._lastEventId) {
      url += `&lastEventId=${encodeURIComponent(this._lastEventId)}`;
    }

    return url;
  }

  private async initiateConnection(): Promise<void> {
    if (!this.ticketProvider || this.intentionalDisconnect) return;

    this.updateState('connecting');

    let ticket: string;
    try {
      ticket = await this.ticketProvider();
    } catch {
      if (this.intentionalDisconnect) return;
      this.handleConnectionFailure();
      return;
    }

    if (this.intentionalDisconnect) return;

    try {
      const wsUrl = this.getWebSocketUrl(ticket);
      const ws = new WebSocket(wsUrl);
      this.socket = ws;

      ws.onopen = () => {
        if (this.socket !== ws) return;
        this.consecutiveFailures = 0;
        this.clearReconnectTimer();
        this.updateState('connected');
      };

      ws.onmessage = (event: MessageEvent) => {
        if (this.socket !== ws) return;
        this.handleMessage(event.data);
      };

      ws.onerror = () => {
        // ws.onclose will be fired immediately afterwards
      };

      ws.onclose = (event: CloseEvent) => {
        if (this.socket === ws) {
          this.socket = null;
        }

        if (this.intentionalDisconnect) {
          this.updateState('disconnected');
          return;
        }

        // Close code 4401: Token expired, immediate reconnect with new ticket, not a failure
        if (event.code === 4401) {
          this.clearReconnectTimer();
          this.reconnectTimer = setTimeout(() => {
            this.initiateConnection();
          }, 0);
          return;
        }

        this.handleConnectionFailure();
      };
    } catch {
      this.handleConnectionFailure();
    }
  }

  private handleConnectionFailure(): void {
    if (this.intentionalDisconnect) return;

    this.consecutiveFailures += 1;
    this.clearReconnectTimer();

    // After 5 consecutive failures: state = 'polling', retry socket every 30s
    if (this.consecutiveFailures >= 5) {
      this.updateState('polling');
      this.reconnectTimer = setTimeout(() => {
        this.initiateConnection();
      }, 30000);
      return;
    }

    this.updateState('reconnecting');

    // Exponential backoff 1, 2, 4, 8, 16, 30s with jitter
    const stepIndex = Math.min(this.consecutiveFailures - 1, BACKOFF_STEPS.length - 1);
    const baseDelay = BACKOFF_STEPS[stepIndex];
    // Jitter: +/- 20%
    const jitter = (Math.random() - 0.5) * 0.4 * baseDelay;
    const delay = Math.max(500, Math.round(baseDelay + jitter));

    this.reconnectTimer = setTimeout(() => {
      this.initiateConnection();
    }, delay);
  }

  private handleMessage(rawData: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawData);
    } catch {
      return;
    }

    const messages = Array.isArray(parsed) ? parsed : [parsed];

    for (const msg of messages) {
      if (!msg || typeof msg !== 'object') continue;

      const rawMsg = msg as {
        type?: ServerMessageType;
        eventId?: string;
        payload?: Record<string, unknown>;
      };

      if (!rawMsg.type) continue;

      // Store eventId if present
      if (rawMsg.eventId) {
        this._lastEventId = rawMsg.eventId;
      }

      // Handle RATE_LIMITED error toast
      if (rawMsg.type === 'ERROR') {
        const payload = rawMsg.payload as
          | { code?: string; message?: string; retryAfterMs?: number }
          | undefined;
        if (payload?.code === 'RATE_LIMITED') {
          const retryAfterMs = payload.retryAfterMs;
          const retrySec = retryAfterMs ? Math.ceil(retryAfterMs / 1000) : 1;
          showToast(`Rate limited. Please retry in ${retrySec}s.`);
        }
      }

      // Handle RESYNC_REQUIRED: notify useAreas to refetch the viewport over HTTP
      if (rawMsg.type === 'RESYNC_REQUIRED') {
        this.resyncHandlers.forEach((handler) => {
          try {
            handler();
          } catch (err) {
            console.error('Error in resync handler', err);
          }
        });
      }

      // Normalize Area DTOs in AREA_SAVED and AREA_UPDATED payloads
      let dispatchedPayload = rawMsg.payload;
      if (rawMsg.type === 'AREA_SAVED' || rawMsg.type === 'AREA_UPDATED') {
        const areaPayload = rawMsg.payload as { area?: unknown; shapeId?: string } | undefined;
        if (areaPayload?.area) {
          dispatchedPayload = {
            ...areaPayload,
            area: mapServerAreaToArea(areaPayload.area),
          };
        }
      }

      // Normalize USER_JOINED payload: extract { user: PresenceUser } if nested
      if (rawMsg.type === 'USER_JOINED' && rawMsg.payload) {
        const joinedPayload = rawMsg.payload as { user?: unknown };
        if (joinedPayload.user && typeof joinedPayload.user === 'object') {
          dispatchedPayload = joinedPayload.user as Record<string, unknown>;
        }
      }

      // Dispatch to typed listeners
      const set = this.handlers.get(rawMsg.type);
      if (set) {
        set.forEach((handler) => {
          try {
            handler(dispatchedPayload as WsPayloadMap[ServerMessageType], rawMsg.eventId);
          } catch (err) {
            console.error(`Error in WebSocket handler for ${rawMsg.type}`, err);
          }
        });
      }
    }
  }
}

export const realWebSocketService = new RealWebSocketService();
