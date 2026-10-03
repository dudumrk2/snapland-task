import type { IWebSocketService } from '../../api/interfaces/IWebSocketService';
import { useCollaborationStore } from '../../store/collaborationStore';
import { useAreasStore } from '../../store/areasStore';

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
    const user = 'user' in payload ? payload.user : payload;
    if (user && user.userId) {
      useCollaborationStore.getState().addPresenceUser(user);
    }
  });

  const unsubLeft = wsService.on('USER_LEFT', (payload) => {
    if (payload.userId) {
      useCollaborationStore.getState().removePresenceUser(payload.userId);
    }
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
    if (
      options.enableProactiveConflict &&
      editingAreaId === payload.area.id &&
      editedCoordinates
    ) {
      const local = areas.find((a) => a.id === editingAreaId);
      areasState.setConflict({
        localArea: {
          id: editingAreaId,
          name: local?.name ?? payload.area.name,
          coordinates: editedCoordinates,
          version: local?.version ?? payload.area.version - 1,
        },
        currentArea: payload.area,
      });
    }
    areasState.updateArea(payload.area);
    if (eventId) useCollaborationStore.getState().setLastEventId(eventId);
  });

  const unsubAreaDeleted = wsService.on('AREA_DELETED', (payload, eventId) => {
    const areasState = useAreasStore.getState();
    const { editingAreaId, editedCoordinates, areas } = areasState;

    // Proactive conflict detection on deletion (HLD §14)
    if (
      options.enableProactiveConflict &&
      editingAreaId === payload.areaId &&
      editedCoordinates
    ) {
      const local = areas.find((a) => a.id === editingAreaId);
      areasState.setConflict({
        localArea: {
          id: payload.areaId,
          name: local?.name ?? 'Deleted Area',
          coordinates: editedCoordinates,
          version: local?.version ?? 1,
        },
        // Synthetic Area representing "deleted on server". Callers can detect
        // this case by checking that currentArea.name ends with '(Deleted)' or
        // by comparing currentArea.version to localArea.version + 1.
        // Empty-string sentinels are used for fields unavailable after deletion.
        currentArea: {
          id: payload.areaId,
          name: `${local?.name || 'Area'} (Deleted on server)`,
          coordinates: local?.coordinates ?? editedCoordinates,
          areaKm2: local?.areaKm2 ?? 0,
          version: (local?.version ?? 1) + 1,
          createdBy: local?.createdBy ?? '',
          lastEditedBy: '',
          createdAt: local?.createdAt ?? '',
          updatedAt: '',
        },
        deletedOnServer: true,
      });
    }

    areasState.deleteArea(payload.areaId);
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
