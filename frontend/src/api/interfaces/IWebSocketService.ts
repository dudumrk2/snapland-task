import type {
  WsMessage,
  ClientMessageType,
  ServerMessageType,
  WsPayloadMap,
} from '@snapland/shared-types';

export type ConnectionState =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'polling'
  | 'disconnected';

export type MessageHandler<T extends ServerMessageType> = (
  payload: WsPayloadMap[T],
  eventId?: string
) => void;

export interface IWebSocketService {
  /** ticketProvider is invoked before EVERY (re)connect — tickets are single-use with a 30 s TTL. */
  connect(ticketProvider: () => Promise<string>): void;
  disconnect(): void;
  send<T extends ClientMessageType>(message: WsMessage<T>): boolean;
  /** Server frames are JSON arrays (micro-batches); the service unpacks them and dispatches per message. */
  on<T extends ServerMessageType>(type: T, handler: MessageHandler<T>): () => void;
  onStateChange(handler: (state: ConnectionState) => void): () => void;
  readonly connectionState: ConnectionState; // 'polling' = degraded mode after 5 consecutive failures
  readonly lastEventId: string | null; // sent as ?lastEventId= on reconnect
}
