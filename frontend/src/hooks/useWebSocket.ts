import { useCallback, useEffect, useRef } from 'react';
import type {
  ClientMessageType,
  Coordinate,
  WsMessage,
} from '@snapland/shared-types';
import { useCollaborationStore } from '../store/collaborationStore';
import { useAreasStore } from '../store/areasStore';
import { useWebSocketContext } from '../providers/WebSocketProvider';
import { useApi } from '../providers/ApiProvider';

export function useWebSocket(autoConnect = true) {
  const { wsService, authApi } = useApi();
  const wsContext = useWebSocketContext();
  const lastCursorSentRef = useRef<number>(0);

  const connectionState = useCollaborationStore((s) => s.connectionState);
  const presenceUsers = useCollaborationStore((s) => s.presenceUsers);
  const remoteCursors = useCollaborationStore((s) => s.remoteCursors);
  const remoteShapes = useCollaborationStore((s) => s.remoteShapes);

  // Fallback lifecycle when outside WebSocketProvider
  useEffect(() => {
    if (wsContext) return;

    const unsubState = wsService.onStateChange((state) => {
      useCollaborationStore.getState().setConnectionState(state);
    });

    const unsubPresence = wsService.on('PRESENCE_SNAPSHOT', (payload) => {
      useCollaborationStore.getState().setPresenceUsers(payload.users);
    });

    const unsubJoined = wsService.on('USER_JOINED', (payload) => {
      useCollaborationStore.getState().addPresenceUser(payload);
    });

    const unsubLeft = wsService.on('USER_LEFT', (payload) => {
      useCollaborationStore.getState().removePresenceUser(payload.userId);
    });

    const unsubCursor = wsService.on('CURSOR_MOVE', (payload) => {
      useCollaborationStore.getState().updateRemoteCursor(payload);
    });

    const unsubDraw = wsService.on('REMOTE_DRAW', (payload) => {
      useCollaborationStore.getState().handleRemoteDraw(payload);
    });

    const unsubAreaSaved = wsService.on('AREA_SAVED', (payload, eventId) => {
      useAreasStore.getState().addArea(payload.area);
      if (payload.shapeId) {
        useCollaborationStore.getState().removeRemoteShape(payload.shapeId);
      }
      if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
    });

    const unsubAreaUpdated = wsService.on('AREA_UPDATED', (payload, eventId) => {
      useAreasStore.getState().updateArea(payload.area);
      if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
    });

    const unsubAreaDeleted = wsService.on('AREA_DELETED', (payload, eventId) => {
      useAreasStore.getState().deleteArea(payload.areaId);
      if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
    });

    if (autoConnect) {
      wsService.connect(async () => {
        return authApi.getWsTicket();
      });
    }

    return () => {
      unsubState();
      unsubPresence();
      unsubJoined();
      unsubLeft();
      unsubCursor();
      unsubDraw();
      unsubAreaSaved();
      unsubAreaUpdated();
      unsubAreaDeleted();
      if (autoConnect) {
        wsService.disconnect();
      }
    };
  }, [wsContext, wsService, authApi, autoConnect]);

  const sendCursorMove = useCallback(
    (coord: Coordinate) => {
      if (wsContext) {
        wsContext.sendCursorMove(coord);
      } else {
        const now = Date.now();
        // Throttle cursor moves to max 10 Hz (every 100ms) as per HLD §9.1
        if (now - lastCursorSentRef.current >= 100) {
          lastCursorSentRef.current = now;
          wsService.send({
            type: 'CURSOR_MOVE',
            payload: { lat: coord.lat, lng: coord.lng },
          });
        }
      }
    },
    [wsContext, wsService]
  );

  const sendMessage = useCallback(
    <T extends ClientMessageType>(msg: WsMessage<T>) => {
      if (wsContext) {
        wsContext.sendMessage(msg);
      } else {
        wsService.send(msg);
      }
    },
    [wsContext, wsService]
  );

  const connect = useCallback(() => {
    if (wsContext) {
      wsContext.connect();
    } else {
      wsService.connect(() => authApi.getWsTicket());
    }
  }, [wsContext, wsService, authApi]);

  const disconnect = useCallback(() => {
    if (wsContext) {
      wsContext.disconnect();
    } else {
      wsService.disconnect();
    }
  }, [wsContext, wsService]);

  return {
    connectionState,
    presenceUsers,
    remoteCursors,
    remoteShapes,
    sendCursorMove,
    sendMessage,
    connect,
    disconnect,
  };
}
