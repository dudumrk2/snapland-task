import { describe, it, expect, beforeEach } from 'vitest';
import { useAreasStore } from '../../../src/store/areasStore';
import type { Area } from '@snapland/shared-types';

const sampleArea: Area = {
  id: 'area-1',
  name: 'Zone A',
  coordinates: [{ lat: 32, lng: 34 }],
  areaKm2: 1.0,
  version: 1,
  createdBy: 'user',
  lastEditedBy: 'user',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('areasStore', () => {
  beforeEach(() => {
    useAreasStore.setState({
      areas: [],
      selectedAreaId: null,
      editingAreaId: null,
      editedCoordinates: null,
      history: [],
      isFetching: false,
      isSaving: false,
      isDeleting: false,
      isLoading: false,
      error: null,
    });
  });

  it('keeps isLoading true when saving while fetching completes', () => {
    const store = useAreasStore.getState();

    // Start saving an area
    store.setSaving(true);
    expect(useAreasStore.getState().isSaving).toBe(true);
    expect(useAreasStore.getState().isLoading).toBe(true);

    // Concurrently, a background map pan fetch finishes and calls setAreas
    store.setAreas([sampleArea]);

    // isFetching is false, but isSaving is still true -> isLoading remains true!
    expect(useAreasStore.getState().isFetching).toBe(false);
    expect(useAreasStore.getState().isSaving).toBe(true);
    expect(useAreasStore.getState().isLoading).toBe(true);

    // Save finishes
    store.setSaving(false);
    expect(useAreasStore.getState().isSaving).toBe(false);
    expect(useAreasStore.getState().isLoading).toBe(false);
  });

  it('addArea inserts new area and upserts existing area by id', () => {
    const store = useAreasStore.getState();

    store.addArea(sampleArea);
    expect(useAreasStore.getState().areas).toHaveLength(1);
    expect(useAreasStore.getState().areas[0].name).toBe('Zone A');

    // Upsert same ID with updated name
    store.addArea({ ...sampleArea, name: 'Zone A Updated', version: 2 });
    expect(useAreasStore.getState().areas).toHaveLength(1);
    expect(useAreasStore.getState().areas[0].name).toBe('Zone A Updated');
    expect(useAreasStore.getState().areas[0].version).toBe(2);
  });

  it('updateArea updates area and clears editing state if editingAreaId matches', () => {
    const store = useAreasStore.getState();
    store.setAreas([sampleArea]);
    store.startEditing('area-1');
    expect(useAreasStore.getState().editingAreaId).toBe('area-1');
    expect(useAreasStore.getState().editedCoordinates).toEqual(sampleArea.coordinates);

    store.updateArea({ ...sampleArea, name: 'Renamed Area' });
    const state = useAreasStore.getState();
    expect(state.areas[0].name).toBe('Renamed Area');
    expect(state.editingAreaId).toBeNull();
    expect(state.editedCoordinates).toBeNull();
  });

  it('deleteArea removes area and cascades to selectedAreaId and editingAreaId', () => {
    const store = useAreasStore.getState();
    store.setAreas([sampleArea]);
    store.selectArea('area-1');
    store.startEditing('area-1');
    expect(useAreasStore.getState().selectedAreaId).toBe('area-1');
    expect(useAreasStore.getState().editingAreaId).toBe('area-1');

    store.deleteArea('area-1');
    const state = useAreasStore.getState();
    expect(state.areas).toHaveLength(0);
    expect(state.selectedAreaId).toBeNull();
    expect(state.editingAreaId).toBeNull();
    expect(state.editedCoordinates).toBeNull();
  });

  it('setError resets all granular loading flags', () => {
    const store = useAreasStore.getState();
    store.setSaving(true);
    store.setFetching(true);
    store.setDeleting(true);
    expect(useAreasStore.getState().isLoading).toBe(true);

    store.setError('Something failed');
    const state = useAreasStore.getState();
    expect(state.error).toBe('Something failed');
    expect(state.isLoading).toBe(false);
    expect(state.isFetching).toBe(false);
    expect(state.isSaving).toBe(false);
    expect(state.isDeleting).toBe(false);
  });
});
