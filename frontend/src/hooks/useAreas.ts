import { useCallback } from 'react';
import type {
  BoundingBox,
  Coordinate,
  UpdateAreaRequest,
} from '@snapland/shared-types';
import { useApi } from '../providers/ApiProvider';
import { useAreasStore } from '../store/areasStore';
import { ConflictError } from '../api/interfaces/IAreaApi';

export function useAreas() {
  const { areaApi } = useApi();
  const {
    areas,
    selectedAreaId,
    editingAreaId,
    editedCoordinates,
    history,
    conflict,
    isLoading,
    error,
    setAreas,
    addArea,
    updateArea: updateStoreArea,
    deleteArea: deleteStoreArea,
    selectArea,
    startEditing,
    setEditedCoordinates,
    cancelEditing,
    setConflict,
    setHistory,
    setLoading,
    setError,
  } = useAreasStore();

  const selectedArea = areas.find((a) => a.id === selectedAreaId) || null;

  const fetchAreasInBounds = useCallback(
    async (bounds: BoundingBox, zoom: number) => {
      setLoading(true);
      setError(null);
      try {
        const page = await areaApi.getAreasInBounds(bounds, zoom);
        setAreas(page.areas);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch areas');
      }
    },
    [areaApi, setAreas, setLoading, setError]
  );

  const createArea = useCallback(
    async (name: string, coordinates: Coordinate[]) => {
      setLoading(true);
      setError(null);
      try {
        const newArea = await areaApi.createArea({ name, coordinates });
        addArea(newArea);
        selectArea(newArea.id);
        return newArea;
      } catch (err: any) {
        setError(err.message || 'Failed to create area');
        throw err;
      }
    },
    [areaApi, addArea, selectArea, setLoading, setError]
  );

  const updateArea = useCallback(
    async (id: string, req: UpdateAreaRequest) => {
      setLoading(true);
      setError(null);
      try {
        const updated = await areaApi.updateArea(id, req);
        updateStoreArea(updated);
        setConflict(null);
        return updated;
      } catch (err: any) {
        if (err instanceof ConflictError) {
          const localArea = areas.find((a) => a.id === id);
          if (localArea) {
            setConflict({
              localArea: {
                id,
                name: req.name ?? localArea.name,
                coordinates: req.coordinates ?? localArea.coordinates,
                version: req.version,
              },
              currentArea: err.currentArea,
            });
          }
        }
        setError(err.message || 'Failed to update area');
        throw err;
      }
    },
    [areaApi, areas, updateStoreArea, setConflict, setLoading, setError]
  );

  const deleteArea = useCallback(
    async (id: string) => {
      setLoading(true);
      setError(null);
      try {
        await areaApi.deleteArea(id);
        deleteStoreArea(id);
      } catch (err: any) {
        setError(err.message || 'Failed to delete area');
        throw err;
      }
    },
    [areaApi, deleteStoreArea, setLoading, setError]
  );

  const fetchHistory = useCallback(
    async (id: string) => {
      try {
        const historyList = await areaApi.getAreaHistory(id);
        setHistory(historyList);
      } catch (err: any) {
        setError(err.message || 'Failed to fetch history');
      }
    },
    [areaApi, setHistory, setError]
  );

  // OCC Conflict Resolution Options (HLD §14)
  // 1. Accept Remote: Discard local edit, adopt remote state
  const resolveAcceptRemote = useCallback(() => {
    if (!conflict) return;
    updateStoreArea(conflict.currentArea);
    setConflict(null);
    cancelEditing();
  }, [conflict, updateStoreArea, setConflict, cancelEditing]);

  // 2. Force Overwrite: re-send local geometry against remote current_version
  const resolveForceOverwrite = useCallback(async () => {
    if (!conflict) return;
    const { localArea, currentArea } = conflict;
    await updateArea(localArea.id, {
      name: localArea.name,
      coordinates: localArea.coordinates,
      version: currentArea.version,
    });
  }, [conflict, updateArea]);

  // 3. Save as New: POST local geometry as a new area
  const resolveSaveAsNew = useCallback(
    async (newName?: string) => {
      if (!conflict) return;
      const { localArea } = conflict;
      await createArea(
        newName || `${localArea.name} (Copy)`,
        localArea.coordinates
      );
      setConflict(null);
      cancelEditing();
    },
    [conflict, createArea, setConflict, cancelEditing]
  );

  return {
    areas,
    selectedArea,
    selectedAreaId,
    editingAreaId,
    editedCoordinates,
    history,
    conflict,
    isLoading,
    error,
    fetchAreasInBounds,
    createArea,
    updateArea,
    deleteArea,
    fetchHistory,
    selectArea,
    startEditing,
    setEditedCoordinates,
    cancelEditing,
    setConflict,
    resolveAcceptRemote,
    resolveForceOverwrite,
    resolveSaveAsNew,
  };
}
