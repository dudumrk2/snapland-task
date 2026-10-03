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

export class WebSocketService implements IWebSocketService {
  private state: ConnectionState = 'disconnected';
  private handlers = new Map<ServerMessageType, Set<MessageHandler<any>>>();
  private stateChangeHandlers = new Set<(state: ConnectionState) => void>();
  private ws: WebSocket | null = null;
  private ticketProvider: (() => Promise<string>) | null = null;
  private _lastEventId: string | null = null;
  private consecutiveFailures = 0;
  private reconnectTimer: any = null;
  private isIntentionallyClosed = false;
  private customBaseUrl?: string;

  private readonly BACKOFF_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000];

  constructor(customBaseUrl?: string) {
    this.customBaseUrl = customBaseUrl;
  }

  get connectionState(): ConnectionState {
    return this.state;
  }

  get lastEventId(): string | null {
    return this._lastEventId;
  }

  connect(ticketProvider: () => Promise<string>): void {
    this.ticketProvider = ticketProvider;
    this.isIntentionallyClosed = false;
    this.attemptConnection();
  }

  disconnect(): void {
    this.isIntentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      // Prevent onclose handler from attempting reconnect
      const socket = this.ws;
      this.ws = null;
      socket.close(1000, 'User disconnect');
    }
    this.consecutiveFailures = 0;
    this.updateState('disconnected');
  }

  send<T extends ClientMessageType>(message: WsMessage<T>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  on<T extends ServerMessageType>(type: T, handler: MessageHandler<T>): () => void {
    let set = this.handlers.get(type);
    if (!set) {
      set = new Set();
      this.handlers.set(type, set);
    }
    set.add(handler);

    return () => {
      const currentSet = this.handlers.get(type);
      if (currentSet) {
        currentSet.delete(handler);
        if (currentSet.size === 0) {
          this.handlers.delete(type);
        }
      }
    };
  }

  onStateChange(handler: (state: ConnectionState) => void): () => void {
    this.stateChangeHandlers.add(handler);
    handler(this.state);

    return () => {
      this.stateChangeHandlers.delete(handler);
    };
  }

  private updateState(newState: ConnectionState): void {
    if (this.state === newState) return;
    this.state = newState;
    this.stateChangeHandlers.forEach((h) => {
      try {
        h(newState);
      } catch (err) {
        console.error('Error in onStateChange handler', err);
      }
    });
  }

  private scheduleReconnect(delayMs: number): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.isIntentionallyClosed) return;

    this.reconnectTimer = setTimeout(() => {
      this.attemptConnection();
    }, delayMs);
  }

  private handleConnectionFailure(): void {
    if (this.isIntentionallyClosed) return;

    this.consecutiveFailures += 1;

    if (this.consecutiveFailures >= 5) {
      this.updateState('polling');
      // After 5 consecutive failures, retry every 30s
      this.scheduleReconnect(30000);
    } else {
      this.updateState('reconnecting');
      const idx = Math.min(this.consecutiveFailures - 1, this.BACKOFF_DELAYS.length - 1);
      const baseDelay = this.BACKOFF_DELAYS[idx];
      // Exponential backoff + jitter (up to 500ms)
      const jitter = Math.random() * 500;
      const delay = Math.min(baseDelay + jitter, 30000);
      this.scheduleReconnect(delay);
    }
  }

  private async attemptConnection(): Promise<void> {
    if (this.isIntentionallyClosed) return;
    if (this.state === 'connected') return;

    if (this.consecutiveFailures >= 5) {
      this.updateState('polling');
    } else if (this.state === 'disconnected') {
      this.updateState('connecting');
    } else {
      this.updateState('reconnecting');
    }

    if (!this.ticketProvider) {
      this.handleConnectionFailure();
      return;
    }

    let ticket: string;
    try {
      ticket = await this.ticketProvider();
    } catch {
      this.handleConnectionFailure();
      return;
    }

    if (this.isIntentionallyClosed) return;

    const wsUrl = this.buildUrl(ticket);

    try {
      const socket = new WebSocket(wsUrl);
      this.ws = socket;

      socket.onopen = () => {
        if (this.ws !== socket) return;
        this.consecutiveFailures = 0;
        this.updateState('connected');
      };

      socket.onmessage = (event: MessageEvent) => {
        if (this.ws !== socket) return;
        this.handleRawFrame(event.data);
      };

      socket.onclose = (event: CloseEvent) => {
        if (this.ws === socket) {
          this.ws = null;
        }

        if (this.isIntentionallyClosed) {
          this.updateState('disconnected');
          return;
        }

        // Close code 4401: token expired (15 min) -> immediate reconnect with fresh ticket, not counted as failure
        if (event.code === 4401) {
          this.updateState('connecting');
          this.scheduleReconnect(0);
          return;
        }

        this.handleConnectionFailure();
      };

      socket.onerror = () => {
        // onclose will handle recovery
      };
    } catch {
      this.handleConnectionFailure();
    }
  }

  private buildUrl(ticket: string): string {
    if (this.customBaseUrl) {
      const separator = this.customBaseUrl.includes('?') ? '&' : '?';
      let url = `${this.customBaseUrl}${separator}ticket=${encodeURIComponent(ticket)}`;
      if (this._lastEventId) {
        url += `&lastEventId=${encodeURIComponent(this._lastEventId)}`;
      }
      return url;
    }

    const isSecure = typeof window !== 'undefined' && window.location.protocol === 'https:';
    const protocol = isSecure ? 'wss:' : 'ws:';
    const host = typeof window !== 'undefined' && window.location.host ? window.location.host : 'localhost:8000';
    let url = `${protocol}//${host}/ws?ticket=${encodeURIComponent(ticket)}`;
    if (this._lastEventId) {
      url += `&lastEventId=${encodeURIComponent(this._lastEventId)}`;
    }
    return url;
  }

  private handleRawFrame(data: any): void {
    try {
      const parsed = typeof data === 'string' ? JSON.parse(data) : data;
      // Server frames are JSON arrays (micro-batches)
      const messages: WsMessage<any>[] = Array.isArray(parsed) ? parsed : [parsed];

      for (const msg of messages) {
        if (!msg || !msg.type) continue;

        // Store eventId from durable events (AREA_* or any message carrying eventId)
        if (msg.eventId) {
          this._lastEventId = msg.eventId;
        }

        // Handle RESYNC_REQUIRED: trigger HTTP viewport refetch
        if (msg.type === 'RESYNC_REQUIRED') {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('snapland:resync_viewport', { detail: msg.payload })
            );
          }
        }

        // Handle ERROR: if RATE_LIMITED, surface notification
        if (msg.type === 'ERROR') {
          const payload = msg.payload as WsPayloadMap['ERROR'];
          if (payload?.code === 'RATE_LIMITED') {
            const sec = payload.retryAfterMs ? Math.ceil(payload.retryAfterMs / 1000) : 60;
            if (typeof window !== 'undefined') {
              window.dispatchEvent(
                new CustomEvent('snapland:toast', {
                  detail: { message: `Drawing action rate limit exceeded. Please wait ${sec}s.` },
                })
              );
            }
          }
        }

        this.dispatch(msg.type, msg.payload, msg.eventId);
      }
    } catch (err) {
      console.error('Failed to parse WebSocket frame', err);
    }
  }

  private dispatch<T extends ServerMessageType>(
    type: T,
    payload: WsPayloadMap[T],
    eventId?: string
  ): void {
    const typeHandlers = this.handlers.get(type);
    if (!typeHandlers) return;

    typeHandlers.forEach((handler) => {
      try {
        handler(payload, eventId);
      } catch (err) {
        console.error(`Error in WebSocket handler for ${type}`, err);
      }
    });
  }
}

export const realWebSocketService = new WebSocketService();
