import { describe, it, expect, beforeEach } from 'vitest';
import { useAreasStore } from '../../../src/store/areasStore';

describe('areasStore granular loading', () => {
  beforeEach(() => {
    useAreasStore.setState({
      areas: [],
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
    store.setAreas([
      {
        id: 'area-1',
        name: 'Zone A',
        coordinates: [{ lat: 32, lng: 34 }],
        areaKm2: 1.0,
        version: 1,
        createdBy: 'user',
        lastEditedBy: 'user',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
    ]);

    // isFetching is false, but isSaving is still true -> isLoading remains true!
    expect(useAreasStore.getState().isFetching).toBe(false);
    expect(useAreasStore.getState().isSaving).toBe(true);
    expect(useAreasStore.getState().isLoading).toBe(true);

    // Save finishes
    store.setSaving(false);
    expect(useAreasStore.getState().isSaving).toBe(false);
    expect(useAreasStore.getState().isLoading).toBe(false);
  });
});
