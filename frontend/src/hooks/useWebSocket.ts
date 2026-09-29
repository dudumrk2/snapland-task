import { useEffect, useRef, useCallback } from 'react';
import type {
  ClientMessageType,
  Coordinate,
  WsMessage,
} from '@snapland/shared-types';
import { useApi } from '../providers/ApiProvider';
import { useCollaborationStore } from '../store/collaborationStore';
import { useAreasStore } from '../store/areasStore';

export function useWebSocket(autoConnect = true) {
  const { wsService, authApi } = useApi();
  const {
    connectionState,
    presenceUsers,
    remoteCursors,
    remoteShapes,
    setConnectionState,
    setPresenceUsers,
    addPresenceUser,
    removePresenceUser,
    updateRemoteCursor,
    handleRemoteDraw,
    removeRemoteShape,
    setLastEventId,
  } = useCollaborationStore();

  const {
    addArea,
    updateArea,
    deleteArea,
    editingAreaId,
    editedCoordinates,
    areas,
    setConflict,
  } = useAreasStore();

  const lastCursorSentRef = useRef<number>(0);

  // Auto-connect and wire event listeners
  useEffect(() => {
    const unsubState = wsService.onStateChange((state) => {
      setConnectionState(state);
    });

    const unsubPresence = wsService.on('PRESENCE_SNAPSHOT', (payload) => {
      setPresenceUsers(payload.users);
    });

    const unsubJoined = wsService.on('USER_JOINED', (payload) => {
      addPresenceUser(payload);
    });

    const unsubLeft = wsService.on('USER_LEFT', (payload) => {
      removePresenceUser(payload.userId);
    });

    const unsubCursor = wsService.on('CURSOR_MOVE', (payload) => {
      updateRemoteCursor(payload);
    });

    const unsubDraw = wsService.on('REMOTE_DRAW', (payload) => {
      handleRemoteDraw(payload);
    });

    const unsubAreaSaved = wsService.on('AREA_SAVED', (payload, eventId) => {
      addArea(payload.area);
      if (payload.shapeId) {
        removeRemoteShape(payload.shapeId);
      }
      if (eventId) setLastEventId(eventId);
    });

    const unsubAreaUpdated = wsService.on('AREA_UPDATED', (payload, eventId) => {
      // Proactive conflict detection (HLD §14)
      if (editingAreaId === payload.area.id && editedCoordinates) {
        const local = areas.find((a) => a.id === editingAreaId);
        if (local) {
          setConflict({
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
      updateArea(payload.area);
      if (eventId) setLastEventId(eventId);
    });

    const unsubAreaDeleted = wsService.on('AREA_DELETED', (payload, eventId) => {
      deleteArea(payload.areaId);
      if (eventId) setLastEventId(eventId);
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
    };
  }, [
    wsService,
    authApi,
    autoConnect,
    setConnectionState,
    setPresenceUsers,
    addPresenceUser,
    removePresenceUser,
    updateRemoteCursor,
    handleRemoteDraw,
    removeRemoteShape,
    setLastEventId,
    addArea,
    updateArea,
    deleteArea,
    editingAreaId,
    editedCoordinates,
    areas,
    setConflict,
  ]);

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

  return {
    connectionState,
    presenceUsers,
    remoteCursors,
    remoteShapes,
    sendCursorMove,
    sendMessage,
    connect: () => wsService.connect(() => authApi.getWsTicket()),
    disconnect: () => wsService.disconnect(),
  };
}
