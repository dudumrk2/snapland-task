import type {
  ClientMessageType,
  ServerMessageType,
  WsMessage,
  WsPayloadMap,
  PresenceUser,
} from '@snapland/shared-types';
import {
  IWebSocketService,
  ConnectionState,
  MessageHandler,
} from '../interfaces/IWebSocketService';

const MOCK_PEERS: PresenceUser[] = [
  { userId: 'peer-user-1', displayName: 'Maya (Architect)' },
  { userId: 'peer-user-2', displayName: 'Dan (Urban Planner)' },
];

export class MockWebSocketService implements IWebSocketService {
  private state: ConnectionState = 'disconnected';
  private handlers = new Map<ServerMessageType, Set<MessageHandler<any>>>();
  private stateChangeHandlers = new Set<(state: ConnectionState) => void>();
  private _lastEventId: string | null = null;
  private mockIntervalTimer: any = null;

  get connectionState(): ConnectionState {
    return this.state;
  }

  get lastEventId(): string | null {
    return this._lastEventId;
  }

  connect(ticketProvider: () => Promise<string>): void {
    if (this.state === 'connected' || this.state === 'connecting') return;

    this.updateState('connecting');

    // Fetch ticket and simulate connection delay
    ticketProvider()
      .then(() => {
        setTimeout(() => {
          this.updateState('connected');
          this.sendPresenceSnapshot();
          this.startMockPeerSimulation();
        }, 100);
      })
      .catch(() => {
        this.updateState('disconnected');
      });
  }

  disconnect(): void {
    if (this.mockIntervalTimer) {
      clearInterval(this.mockIntervalTimer);
      this.mockIntervalTimer = null;
    }
    this.updateState('disconnected');
  }

  send<T extends ClientMessageType>(message: WsMessage<T>): void {
    if (this.state !== 'connected') return;

    // Handle client messages locally in mock
    switch (message.type) {
      case 'DRAW_COMMIT': {
        const payload = message.payload as WsPayloadMap['DRAW_COMMIT'];
        const eventId = `${Date.now()}-0`;
        this._lastEventId = eventId;
        // Echo AREA_SAVED to subscribers
        const areaSavedPayload: WsPayloadMap['AREA_SAVED'] = {
          area: {
            id: `area-${Date.now()}`,
            name: payload.name,
            coordinates: payload.points,
            areaKm2: 1.0,
            version: 1,
            createdBy: 'currentUser',
            lastEditedBy: 'currentUser',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
          shapeId: payload.shapeId,
        };
        this.dispatch('AREA_SAVED', areaSavedPayload, eventId);
        break;
      }
      case 'DRAW_CANCEL': {
        break;
      }
      case 'CURSOR_MOVE': {
        break;
      }
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
    set.add(handler);

    return () => {
      set.delete(handler);
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
    this.state = newState;
    this.stateChangeHandlers.forEach((handler) => handler(newState));
  }

  private dispatch<T extends ServerMessageType>(
    type: T,
    payload: WsPayloadMap[T],
    eventId?: string
  ): void {
    const set = this.handlers.get(type);
    if (set) {
      set.forEach((handler) => handler(payload, eventId));
    }
  }

  private sendPresenceSnapshot(): void {
    this.dispatch('PRESENCE_SNAPSHOT', {
      users: [...MOCK_PEERS],
    });
  }

  private startMockPeerSimulation(): void {
    if (this.mockIntervalTimer) clearInterval(this.mockIntervalTimer);

    let tick = 0;
    this.mockIntervalTimer = setInterval(() => {
      if (this.state !== 'connected') return;
      tick++;

      // Every few seconds, simulate gentle peer cursor movement around Tel Aviv
      const angle = (tick * 0.1) % (2 * Math.PI);
      const latOffset = Math.sin(angle) * 0.005;
      const lngOffset = Math.cos(angle) * 0.005;

      this.dispatch('CURSOR_MOVE', {
        userId: 'peer-user-1',
        lat: 32.0853 + latOffset,
        lng: 34.7818 + lngOffset,
      });
    }, 2000);
  }
}

export const mockWebSocketService = new MockWebSocketService();
