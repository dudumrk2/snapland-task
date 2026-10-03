import { describe, it, expect, beforeEach } from 'vitest';
import { useCollaborationStore } from '../../../src/store/collaborationStore';

describe('collaborationStore', () => {
  beforeEach(() => {
    useCollaborationStore.setState({
      connectionState: 'connected',
      presenceUsers: [],
      remoteCursors: {},
      remoteShapes: {},
      lastEventId: null,
    });
  });

  it('prunes orphaned remote cursors and shapes when setPresenceUsers is called', () => {
    // Populate store with users, cursors, and shapes
    useCollaborationStore.setState({
      presenceUsers: [
        { userId: 'u1', displayName: 'User 1', color: '#111' },
        { userId: 'u2', displayName: 'User 2', color: '#222' },
      ],
      remoteCursors: {
        u1: { userId: 'u1', lat: 32.1, lng: 34.8, updatedAt: Date.now() },
        u2: { userId: 'u2', lat: 32.2, lng: 34.9, updatedAt: Date.now() },
      },
      remoteShapes: {
        'shape-u1': { shapeId: 'shape-u1', userId: 'u1', points: [{ lat: 32.1, lng: 34.8 }] },
        'shape-u2': { shapeId: 'shape-u2', userId: 'u2', points: [{ lat: 32.2, lng: 34.9 }] },
      },
    });

    // New snapshot arrives where u2 has left
    useCollaborationStore.getState().setPresenceUsers([
      { userId: 'u1', displayName: 'User 1', color: '#111' },
    ]);

    const state = useCollaborationStore.getState();
    expect(state.presenceUsers).toHaveLength(1);
    expect(state.remoteCursors['u1']).toBeDefined();
    expect(state.remoteCursors['u2']).toBeUndefined();
    expect(state.remoteShapes['shape-u1']).toBeDefined();
    expect(state.remoteShapes['shape-u2']).toBeUndefined();
  });

  it('clears remote cursors and shapes when connectionState switches to disconnected, polling, or reconnecting', () => {
    useCollaborationStore.setState({
      remoteCursors: {
        u1: { userId: 'u1', lat: 32.1, lng: 34.8, updatedAt: Date.now() },
      },
      remoteShapes: {
        'shape-u1': { shapeId: 'shape-u1', userId: 'u1', points: [{ lat: 32.1, lng: 34.8 }] },
      },
    });

    useCollaborationStore.getState().setConnectionState('reconnecting');
    let state = useCollaborationStore.getState();
    expect(state.remoteCursors).toEqual({});
    expect(state.remoteShapes).toEqual({});

    // Reset and test polling
    useCollaborationStore.setState({
      remoteCursors: {
        u1: { userId: 'u1', lat: 32.1, lng: 34.8, updatedAt: Date.now() },
      },
      remoteShapes: {
        'shape-u1': { shapeId: 'shape-u1', userId: 'u1', points: [{ lat: 32.1, lng: 34.8 }] },
      },
    });

    useCollaborationStore.getState().setConnectionState('polling');
    state = useCollaborationStore.getState();
    expect(state.remoteCursors).toEqual({});
    expect(state.remoteShapes).toEqual({});

    // Reset and test disconnected
    useCollaborationStore.setState({
      presenceUsers: [{ userId: 'u1', displayName: 'User 1', color: '#111' }],
      remoteCursors: {
        u1: { userId: 'u1', lat: 32.1, lng: 34.8, updatedAt: Date.now() },
      },
    });

    useCollaborationStore.getState().setConnectionState('disconnected');
    state = useCollaborationStore.getState();
    expect(state.remoteCursors).toEqual({});
    expect(state.remoteShapes).toEqual({});
    expect(state.presenceUsers).toEqual([]);
  });
});
