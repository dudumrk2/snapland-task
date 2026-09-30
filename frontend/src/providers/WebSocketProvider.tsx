import React, { createContext, useContext, useEffect, useRef, useCallback, ReactNode } from 'react';
import type { ClientMessageType, Coordinate, WsMessage } from '@snapland/shared-types';
import { useApi } from './ApiProvider';
import { useCollaborationStore } from '../store/collaborationStore';
import { useAreasStore } from '../store/areasStore';

interface WebSocketContextValue {
  sendCursorMove: (coord: Coordinate) => void;
  sendMessage: <T extends ClientMessageType>(msg: WsMessage<T>) => void;
  connect: () => void;
  disconnect: () => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export const WebSocketProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { wsService, authApi } = useApi();
  const lastCursorSentRef = useRef<number>(0);

  useEffect(() => {
    // 1. Subscribe to connection state changes
    const unsubState = wsService.onStateChange((state) => {
      useCollaborationStore.getState().setConnectionState(state);
    });

    // 2. Presence
    const unsubPresence = wsService.on('PRESENCE_SNAPSHOT', (payload) => {
      useCollaborationStore.getState().setPresenceUsers(payload.users);
    });

    const unsubJoined = wsService.on('USER_JOINED', (payload) => {
      useCollaborationStore.getState().addPresenceUser(payload);
    });

    const unsubLeft = wsService.on('USER_LEFT', (payload) => {
      useCollaborationStore.getState().removePresenceUser(payload.userId);
    });

    // 3. Cursors & drawing
    const unsubCursor = wsService.on('CURSOR_MOVE', (payload) => {
      useCollaborationStore.getState().updateRemoteCursor(payload);
    });

    const unsubDraw = wsService.on('REMOTE_DRAW', (payload) => {
      useCollaborationStore.getState().handleRemoteDraw(payload);
    });

    // 4. Area sync & proactive OCC conflict detection
    const unsubAreaSaved = wsService.on('AREA_SAVED', (payload, eventId) => {
      useAreasStore.getState().addArea(payload.area);
      if (payload.shapeId) {
        useCollaborationStore.getState().removeRemoteShape(payload.shapeId);
      }
      if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
    });

    const unsubAreaUpdated = wsService.on('AREA_UPDATED', (payload, eventId) => {
      const areasState = useAreasStore.getState();
      const { editingAreaId, editedCoordinates, areas } = areasState;

      // Proactive conflict detection (HLD §14)
      if (editingAreaId === payload.area.id && editedCoordinates) {
        const local = areas.find((a) => a.id === editingAreaId);
        if (local) {
          areasState.setConflict({
            localArea: {
              id: local.id,
              name: local.name,
              coordinates: editedCoordinates,
              version: local.version,
            },
            currentArea: payload.area,
          });
        }
      }
      areasState.updateArea(payload.area);
      if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
    });

    const unsubAreaDeleted = wsService.on('AREA_DELETED', (payload, eventId) => {
      useAreasStore.getState().deleteArea(payload.areaId);
      if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
    });

    // Auto-connect once on mount
    wsService.connect(async () => {
      return authApi.getWsTicket();
    });

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
      wsService.disconnect();
    };
  }, [wsService, authApi]);

  const sendCursorMove = useCallback(
    (coord: Coordinate) => {
      const now = Date.now();
      // Throttle cursor moves to max 10 Hz (every 100ms) as per HLD §9.1
      if (now - lastCursorSentRef.current >= 100) {
        lastCursorSentRef.current = now;
        wsService.send({
          type: 'CURSOR_MOVE',
          payload: { lat: coord.lat, lng: coord.lng },
        });
      }
    },
    [wsService]
  );

  const sendMessage = useCallback(
    <T extends ClientMessageType>(msg: WsMessage<T>) => {
      wsService.send(msg);
    },
    [wsService]
  );

  const connect = useCallback(() => {
    wsService.connect(() => authApi.getWsTicket());
  }, [wsService, authApi]);

  const disconnect = useCallback(() => {
    wsService.disconnect();
  }, [wsService]);

  return (
    <WebSocketContext.Provider value={{ sendCursorMove, sendMessage, connect, disconnect }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocketContext = () => {
  return useContext(WebSocketContext);
};
