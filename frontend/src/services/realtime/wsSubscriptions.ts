import type { IWebSocketService } from '../../api/interfaces/IWebSocketService';
import { useCollaborationStore } from '../../store/collaborationStore';
import { useAreasStore } from '../../store/areasStore';
import { normalizeArea } from '../../api/http/areaApi';

export interface SubscriptionOptions {
  enableProactiveConflict?: boolean;
}

/**
 * Registers all real-time WebSocket event listeners to synchronize
 * collaboration and area stores.
 * Returns an unsubscription callback to cleanly detach all handlers.
 */
export function setupWebSocketSubscriptions(
  wsService: IWebSocketService,
  options: SubscriptionOptions = { enableProactiveConflict: true }
): () => void {
  // 1. Connection state changes
  const unsubState = wsService.onStateChange((state) => {
    useCollaborationStore.getState().setConnectionState(state);
  });

  // 2. Presence
  const unsubPresence = wsService.on('PRESENCE_SNAPSHOT', (payload) => {
    useCollaborationStore.getState().setPresenceUsers(payload.users);
  });

  const unsubJoined = wsService.on('USER_JOINED', (payload) => {
    useCollaborationStore.getState().addPresenceUser(payload.user);
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
    const area = normalizeArea(payload.area);
    useAreasStore.getState().addArea(area);
    if (payload.shapeId) {
      useCollaborationStore.getState().removeRemoteShape(payload.shapeId);
    }
    if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
  });

  const unsubAreaUpdated = wsService.on('AREA_UPDATED', (payload, eventId) => {
    const area = normalizeArea(payload.area);
    const areasState = useAreasStore.getState();
    const { editingAreaId, editedCoordinates, areas } = areasState;

    // Proactive conflict detection (HLD §14)
    if (
      options.enableProactiveConflict &&
      editingAreaId === area.id &&
      editedCoordinates
    ) {
      const local = areas.find((a) => a.id === editingAreaId);
      if (local) {
        areasState.setConflict({
          localArea: {
            id: local.id,
            name: local.name,
            coordinates: editedCoordinates,
            version: local.version,
          },
          currentArea: area,
        });
      }
    }
    areasState.updateArea(area);
    if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
  });

  const unsubAreaDeleted = wsService.on('AREA_DELETED', (payload, eventId) => {
    const areasState = useAreasStore.getState();
    const { editingAreaId, editedCoordinates, areas } = areasState;

    // Proactive conflict detection if the area being edited was deleted remotely
    if (
      options.enableProactiveConflict &&
      editingAreaId === payload.areaId &&
      editedCoordinates
    ) {
      const local = areas.find((a) => a.id === editingAreaId);
      if (local) {
        areasState.setConflict({
          localArea: {
            id: local.id,
            name: local.name,
            coordinates: editedCoordinates,
            version: local.version,
          },
          currentArea: {
            ...local,
            version: local.version + 1,
            name: `${local.name} (Deleted remotely)`,
          },
        });
      }
    }

    useAreasStore.getState().deleteArea(payload.areaId);
    if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
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
  };
}
