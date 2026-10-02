import { useCallback, useRef } from 'react';
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
    isFetching,
    isSaving,
    isDeleting,
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
    setFetching,
    setSaving,
    setDeleting,
    setError,
  } = useAreasStore();

  const selectedArea = areas.find((a) => a.id === selectedAreaId) || null;
  const fetchRequestIdRef = useRef<number>(0);

  const fetchAreasInBounds = useCallback(
    async (bounds: BoundingBox, zoom: number) => {
      const requestId = ++fetchRequestIdRef.current;
      setFetching(true);
      setError(null);
      try {
        const page = await areaApi.getAreasInBounds(bounds, zoom);
        // Ignore stale, out-of-order responses
        if (requestId !== fetchRequestIdRef.current) return;

        // Preserve area currently being edited so it doesn't vanish on pan
        const currentEditingId = useAreasStore.getState().editingAreaId;
        const currentAreas = useAreasStore.getState().areas;
        const editingArea = currentEditingId
          ? currentAreas.find((a) => a.id === currentEditingId)
          : null;

        if (editingArea && !page.areas.some((a) => a.id === editingArea.id)) {
          setAreas([editingArea, ...page.areas]);
        } else {
          setAreas(page.areas);
        }
      } catch (err: unknown) {
        if (requestId === fetchRequestIdRef.current) {
          const msg = err instanceof Error ? err.message : 'Failed to fetch areas';
          setError(msg);
        }
      } finally {
        if (requestId === fetchRequestIdRef.current) {
          setFetching(false);
        }
      }
    },
    [areaApi, setAreas, setFetching, setError]
  );

  const createArea = useCallback(
    async (name: string, coordinates: Coordinate[], shapeId?: string) => {
      setSaving(true);
      setError(null);
      try {
        const newArea = await areaApi.createArea({
          name,
          coordinates,
          ...(shapeId ? { shapeId } : {}),
        } as Parameters<typeof areaApi.createArea>[0]);
        addArea(newArea);
        selectArea(newArea.id);
        return newArea;
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to create area';
        setError(msg);
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [areaApi, addArea, selectArea, setSaving, setError]
  );

  const updateArea = useCallback(
    async (id: string, req: UpdateAreaRequest) => {
      setSaving(true);
      setError(null);
      try {
        const updated = await areaApi.updateArea(id, req);
        updateStoreArea(updated);
        setConflict(null);
        return updated;
      } catch (err: unknown) {
        if (err instanceof ConflictError) {
          const currentAreas = useAreasStore.getState().areas;
          const localArea = currentAreas.find((a) => a.id === id);
          setConflict({
            localArea: {
              id,
              name: req.name ?? localArea?.name ?? err.currentArea.name,
              coordinates: req.coordinates ?? localArea?.coordinates ?? err.currentArea.coordinates,
              version: req.version,
            },
            currentArea: err.currentArea,
          });
        }
        const msg = err instanceof Error ? err.message : 'Failed to update area';
        setError(msg);
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [areaApi, updateStoreArea, setConflict, setSaving, setError]
  );

  const deleteArea = useCallback(
    async (id: string) => {
      setDeleting(true);
      setError(null);
      try {
        await areaApi.deleteArea(id);
        deleteStoreArea(id);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to delete area';
        setError(msg);
        throw err;
      } finally {
        setDeleting(false);
      }
    },
    [areaApi, deleteStoreArea, setDeleting, setError]
  );

  const fetchHistory = useCallback(
    async (id: string) => {
      try {
        const historyList = await areaApi.getAreaHistory(id);
        setHistory(historyList);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to fetch history';
        setError(msg);
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
    try {
      await updateArea(localArea.id, {
        name: localArea.name,
        coordinates: localArea.coordinates,
        version: currentArea.version,
      });
      setConflict(null);
      cancelEditing();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Force overwrite failed';
      setError(msg);
      throw err;
    }
  }, [conflict, updateArea, setConflict, cancelEditing, setError]);

  // 3. Save as New: POST local geometry as a new area
  const resolveSaveAsNew = useCallback(
    async (newName?: string) => {
      if (!conflict) return;
      const { localArea } = conflict;
      try {
        await createArea(
          newName || `${localArea.name} (Copy)`,
          localArea.coordinates
        );
        setConflict(null);
        cancelEditing();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Save as new failed';
        setError(msg);
        throw err;
      }
    },
    [conflict, createArea, setConflict, cancelEditing, setError]
  );

  return {
    areas,
    selectedArea,
    selectedAreaId,
    editingAreaId,
    editedCoordinates,
    history,
    conflict,
    isFetching,
    isSaving,
    isDeleting,
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
