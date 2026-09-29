import { Coordinate } from './geo';
import { Area } from './area';

export type ClientMessageType = 'DRAW_START' | 'DRAW_UPDATE' | 'DRAW_COMMIT' | 'DRAW_CANCEL' | 'CURSOR_MOVE';
export type ServerMessageType =
  | 'REMOTE_DRAW' | 'CURSOR_MOVE'
  | 'AREA_SAVED' | 'AREA_UPDATED' | 'AREA_DELETED'
  | 'USER_JOINED' | 'USER_LEFT' | 'PRESENCE_SNAPSHOT'
  | 'RESYNC_REQUIRED' | 'ERROR';
export type WsMessageType = ClientMessageType | ServerMessageType;

export interface PresenceUser { userId: string; displayName: string; }

export interface WsPayloadMap {
  // client → server
  DRAW_START:   { shapeId: string; point: Coordinate };
  DRAW_UPDATE:  { shapeId: string; seq: number; fromIndex: number; append: Coordinate[] };   // delta, not full ring
  DRAW_COMMIT:  { shapeId: string; name: string; points: Coordinate[] };                     // full ring, authoritative
  DRAW_CANCEL:  { shapeId: string };
  // both directions (server adds userId)
  CURSOR_MOVE:  { lat: number; lng: number; userId?: string };
  // server → client
  REMOTE_DRAW:  { userId: string; shapeId: string; phase: 'start' | 'update' | 'cancel';
                  seq: number; fromIndex: number; append: Coordinate[] };
  AREA_SAVED:   { area: Area; shapeId?: string };          // shapeId lets peers drop the matching preview
  AREA_UPDATED: { area: Area };
  AREA_DELETED: { areaId: string };
  USER_JOINED:  PresenceUser;
  USER_LEFT:    { userId: string };
  PRESENCE_SNAPSHOT: { users: PresenceUser[] };
  RESYNC_REQUIRED: Record<string, never>;
  ERROR:        { code: string; message: string; retryAfterMs?: number };
}

export interface WsMessage<T extends WsMessageType = WsMessageType> {
  type: T;
  payload: WsPayloadMap[T];
  eventId?: string;           // present on durable events (Redis Streams id); clients store the latest
}
