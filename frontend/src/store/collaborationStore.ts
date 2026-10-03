import { create } from 'zustand';
import type {
  PresenceUser,
  Coordinate,
  WsPayloadMap,
} from '@snapland/shared-types';
import type { ConnectionState } from '../api/interfaces/IWebSocketService';

export interface RemoteCursor {
  lat: number;
  lng: number;
  userId: string;
  displayName?: string;
  updatedAt: number;
}

export interface RemoteShape {
  userId: string;
  shapeId: string;
  points: Coordinate[];
}

export interface CollaborationState {
  connectionState: ConnectionState;
  presenceUsers: PresenceUser[];
  remoteCursors: Record<string, RemoteCursor>;
  remoteShapes: Record<string, RemoteShape>;
  lastEventId: string | null;

  setConnectionState: (state: ConnectionState) => void;
  setPresenceUsers: (users: PresenceUser[]) => void;
  addPresenceUser: (user: PresenceUser) => void;
  removePresenceUser: (userId: string) => void;
  updateRemoteCursor: (cursor: { lat: number; lng: number; userId?: string }) => void;
  handleRemoteDraw: (payload: WsPayloadMap['REMOTE_DRAW']) => void;
  removeRemoteShape: (shapeId: string) => void;
  setLastEventId: (id: string | null) => void;
}

export const useCollaborationStore = create<CollaborationState>((set) => ({
  connectionState: 'disconnected',
  presenceUsers: [],
  remoteCursors: {},
  remoteShapes: {},
  lastEventId: null,

  setConnectionState: (connectionState) => set({ connectionState }),
  setPresenceUsers: (presenceUsers) => set({ presenceUsers }),
  addPresenceUser: (user) =>
    set((state) => {
      if (state.presenceUsers.some((u) => u.userId === user.userId)) {
        return state;
      }
      return { presenceUsers: [...state.presenceUsers, user] };
    }),
  removePresenceUser: (userId) =>
    set((state) => {
      const nextCursors = { ...state.remoteCursors };
      delete nextCursors[userId];
      const nextShapes = { ...state.remoteShapes };
      Object.keys(nextShapes).forEach((shapeId) => {
        if (nextShapes[shapeId].userId === userId) {
          delete nextShapes[shapeId];
        }
      });
      return {
        presenceUsers: state.presenceUsers.filter((u) => u.userId !== userId),
        remoteCursors: nextCursors,
        remoteShapes: nextShapes,
      };
    }),
  updateRemoteCursor: (cursor) => {
    if (!cursor.userId) return;
    set((state) => {
      const user = state.presenceUsers.find((u) => u.userId === cursor.userId);
      return {
        remoteCursors: {
          ...state.remoteCursors,
          [cursor.userId!]: {
            lat: cursor.lat,
            lng: cursor.lng,
            userId: cursor.userId!,
            displayName: user?.displayName,
            updatedAt: Date.now(),
          },
        },
      };
    });
  },
  handleRemoteDraw: (payload) =>
    set((state) => {
      const { shapeId, phase, append, fromIndex, userId } = payload;
      if (phase === 'cancel') {
        const next = { ...state.remoteShapes };
        delete next[shapeId];
        return { remoteShapes: next };
      }

      if (phase === 'start') {
        return {
          remoteShapes: {
            ...state.remoteShapes,
            [shapeId]: {
              userId,
              shapeId,
              points: append || [],
            },
          },
        };
      }

      // update
      const existing = state.remoteShapes[shapeId];
      if (!existing) {
        // If start was missed, recover by adopting the incoming points
        return {
          remoteShapes: {
            ...state.remoteShapes,
            [shapeId]: {
              userId,
              shapeId,
              points: append || [],
            },
          },
        };
      }

      // Delta check: verify fromIndex matches local points length or resync
      if (existing.points.length !== fromIndex) {
        // If delta gap detected, resync by appending or replacing to avoid frozen ghost shapes
        if (fromIndex === 0) {
          return {
            remoteShapes: {
              ...state.remoteShapes,
              [shapeId]: { ...existing, points: append || [] },
            },
          };
        }
        return state;
      }

      return {
        remoteShapes: {
          ...state.remoteShapes,
          [shapeId]: {
            ...existing,
            points: [...existing.points, ...(append || [])],
          },
        },
      };
    }),
  removeRemoteShape: (shapeId) =>
    set((state) => {
      const next = { ...state.remoteShapes };
      delete next[shapeId];
      return { remoteShapes: next };
    }),
  setLastEventId: (lastEventId) => set({ lastEventId }),
}));
