import { create } from 'zustand';
import type { Area, AreaVersion, Coordinate } from '@snapland/shared-types';

export interface AreaConflict {
  localArea: {
    id: string;
    name: string;
    coordinates: Coordinate[];
    version: number;
  };
  currentArea: Area;
}

export interface AreasState {
  areas: Area[];
  selectedAreaId: string | null;
  editingAreaId: string | null;
  editedCoordinates: Coordinate[] | null;
  history: AreaVersion[];
  conflict: AreaConflict | null;
  isLoading: boolean;
  error: string | null;

  setAreas: (areas: Area[]) => void;
  addArea: (area: Area) => void;
  updateArea: (area: Area) => void;
  deleteArea: (id: string) => void;
  selectArea: (id: string | null) => void;
  startEditing: (id: string) => void;
  setEditedCoordinates: (coords: Coordinate[] | null) => void;
  cancelEditing: () => void;
  setConflict: (conflict: AreaConflict | null) => void;
  setHistory: (history: AreaVersion[]) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAreasStore = create<AreasState>((set) => ({
  areas: [],
  selectedAreaId: null,
  editingAreaId: null,
  editedCoordinates: null,
  history: [],
  conflict: null,
  isLoading: false,
  error: null,

  setAreas: (areas) => set({ areas, isLoading: false, error: null }),
  addArea: (area) =>
    set((state) => {
      const exists = state.areas.some((a) => a.id === area.id);
      const updated = exists
        ? state.areas.map((a) => (a.id === area.id ? area : a))
        : [area, ...state.areas];
      return { areas: updated, isLoading: false, error: null };
    }),
  updateArea: (area) =>
    set((state) => {
      const updated = state.areas.map((a) => (a.id === area.id ? area : a));
      return {
        areas: updated,
        editingAreaId: state.editingAreaId === area.id ? null : state.editingAreaId,
        editedCoordinates:
          state.editingAreaId === area.id ? null : state.editedCoordinates,
        isLoading: false,
        error: null,
      };
    }),
  deleteArea: (id) =>
    set((state) => ({
      areas: state.areas.filter((a) => a.id !== id),
      selectedAreaId: state.selectedAreaId === id ? null : state.selectedAreaId,
      editingAreaId: state.editingAreaId === id ? null : state.editingAreaId,
      editedCoordinates:
        state.editingAreaId === id ? null : state.editedCoordinates,
      isLoading: false,
      error: null,
    })),
  selectArea: (id) =>
    set({
      selectedAreaId: id,
      editingAreaId: null,
      editedCoordinates: null,
      history: [],
    }),
  startEditing: (id) =>
    set((state) => {
      const area = state.areas.find((a) => a.id === id);
      return {
        selectedAreaId: id,
        editingAreaId: id,
        editedCoordinates: area ? [...area.coordinates] : null,
      };
    }),
  setEditedCoordinates: (coords) => set({ editedCoordinates: coords }),
  cancelEditing: () =>
    set({
      editingAreaId: null,
      editedCoordinates: null,
    }),
  setConflict: (conflict) => set({ conflict }),
  setHistory: (history) => set({ history, isLoading: false, error: null }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error, isLoading: false }),
}));
