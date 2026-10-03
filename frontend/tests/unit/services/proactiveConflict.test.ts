import { describe, it, expect, vi, beforeEach } from 'vitest';
import { setupWebSocketSubscriptions } from '../../../src/services/realtime/wsSubscriptions';
import { useAreasStore } from '../../../src/store/areasStore';
import { MockWebSocketService } from '../../../src/api/mock/mockWebSocketService';
import type { Area } from '@snapland/shared-types';

describe('Proactive Conflict Detection (HLD §14)', () => {
  let mockWs: MockWebSocketService;

  beforeEach(() => {
    mockWs = new MockWebSocketService();
    useAreasStore.getState().setConflict(null);
    useAreasStore.getState().cancelEditing();

    const existingArea: Area = {
      id: 'area-conf-1',
      name: 'Alpha Zone',
      coordinates: [
        { lat: 32.0, lng: 34.7 },
        { lat: 32.1, lng: 34.7 },
        { lat: 32.1, lng: 34.8 },
      ],
      areaKm2: 1.0,
      version: 1,
      createdBy: 'u1',
      lastEditedBy: 'u1',
      createdAt: '2026-10-01T00:00:00Z',
      updatedAt: '2026-10-01T00:00:00Z',
    };

    useAreasStore.getState().setAreas([existingArea]);
  });

  it('immediately sets conflict when AREA_UPDATED arrives for an actively edited polygon', () => {
    setupWebSocketSubscriptions(mockWs, { enableProactiveConflict: true });

    // User starts editing area-conf-1
    useAreasStore.getState().startEditing('area-conf-1');
    const localEditedCoords = [
      { lat: 32.05, lng: 34.75 },
      { lat: 32.15, lng: 34.75 },
      { lat: 32.15, lng: 34.85 },
    ];
    useAreasStore.getState().setEditedCoordinates(localEditedCoords);

    expect(useAreasStore.getState().conflict).toBeNull();

    // Peer edits and updates the same area remotely -> WebSocket delivers AREA_UPDATED
    const remoteUpdatedArea: Area = {
      id: 'area-conf-1',
      name: 'Alpha Zone (Peer Edit)',
      coordinates: [
        { lat: 32.0, lng: 34.7 },
        { lat: 32.2, lng: 34.7 },
        { lat: 32.2, lng: 34.9 },
      ],
      areaKm2: 1.8,
      version: 2,
      createdBy: 'u1',
      lastEditedBy: 'peer-user-2',
      createdAt: '2026-10-01T00:00:00Z',
      updatedAt: '2026-10-01T01:00:00Z',
    };

    // Simulate dispatching AREA_UPDATED through the WS service
    (mockWs as any).dispatch('AREA_UPDATED', { area: remoteUpdatedArea }, 'stream-99');

    // Proactive conflict MUST be set immediately without waiting for user to click save!
    const conflict = useAreasStore.getState().conflict;
    expect(conflict).not.toBeNull();
    expect(conflict?.localArea.id).toBe('area-conf-1');
    expect(conflict?.localArea.version).toBe(1);
    expect(conflict?.localArea.coordinates).toEqual(localEditedCoords);
    expect(conflict?.currentArea.version).toBe(2);
    expect(conflict?.currentArea.name).toBe('Alpha Zone (Peer Edit)');
  });

  it('does NOT trigger conflict if the updated area is not being edited locally', () => {
    setupWebSocketSubscriptions(mockWs, { enableProactiveConflict: true });

    // User is editing area-conf-1
    useAreasStore.getState().startEditing('area-conf-1');
    useAreasStore.getState().setEditedCoordinates([{ lat: 32.05, lng: 34.75 }]);

    // Remote update for a different area arrives
    const otherArea: Area = {
      id: 'different-area',
      name: 'Beta',
      coordinates: [],
      areaKm2: 0.5,
      version: 2,
      createdBy: 'u2',
      lastEditedBy: 'u2',
      createdAt: '2026-10-01T00:00:00Z',
      updatedAt: '2026-10-01T01:00:00Z',
    };

    (mockWs as any).dispatch('AREA_UPDATED', { area: otherArea }, 'stream-100');

    expect(useAreasStore.getState().conflict).toBeNull();
  });
});
