import { useState, useCallback, useRef, useEffect } from 'react';
import type { Coordinate, Area } from '@snapland/shared-types';
import {
  calculatePolygonAreaKm2,
  formatArea,
} from '../utils/areaCalculation';
import {
  removeDuplicateConsecutive,
  validatePolygonCoordinates,
} from '../utils/geoUtils';
import { useApi } from '../providers/ApiProvider';
import { useAreas } from './useAreas';

export interface UseDrawingOptions {
  onPolygonCreated?: (coordinates: Coordinate[]) => void;
}

export function useDrawing(options?: UseDrawingOptions) {
  const { wsService } = useApi();
  const { createArea, selectArea } = useAreas();

  const [isDrawing, setIsDrawing] = useState(false);
  const [points, setPoints] = useState<Coordinate[]>([]);
  const [cursorPoint, setCursorPoint] = useState<Coordinate | null>(null);
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const isDrawingRef = useRef<boolean>(false);
  const pointsRef = useRef<Coordinate[]>([]);
  const shapeIdRef = useRef<string | null>(null);
  const seqRef = useRef<number>(0);
  const lastUpdateSentRef = useRef<number>(0);
  const pendingAppendRef = useRef<Coordinate[]>([]);
  const fromIndexRef = useRef<number>(0);
  const throttleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingCommitRef = useRef<{
    shapeId: string;
    resolve: (area?: Area) => void;
    reject: (err: Error) => void;
    timeoutId: ReturnType<typeof setTimeout>;
  } | null>(null);

  // Compute live approximate area
  const previewPoints =
    cursorPoint && points.length >= 2 ? [...points, cursorPoint] : points;
  const approxAreaKm2 = calculatePolygonAreaKm2(previewPoints);
  const formattedApproxArea = formatArea(approxAreaKm2, true);

  const startDrawing = useCallback(() => {
    if (throttleTimerRef.current) {
      clearTimeout(throttleTimerRef.current);
      throttleTimerRef.current = null;
    }
    const shapeId = `shape-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    shapeIdRef.current = shapeId;
    seqRef.current = 0;
    fromIndexRef.current = 0;
    pendingAppendRef.current = [];
    isDrawingRef.current = true;
    pointsRef.current = [];

    setPoints([]);
    setCursorPoint(null);
    setValidationError(null);
    setIsSaveModalOpen(false);
    setIsDrawing(true);
  }, []);

  const flushDeltaUpdate = useCallback(() => {
    if (throttleTimerRef.current) {
      clearTimeout(throttleTimerRef.current);
      throttleTimerRef.current = null;
    }
    if (!shapeIdRef.current || pendingAppendRef.current.length === 0) return;

    seqRef.current += 1;
    const deltaPayload = {
      shapeId: shapeIdRef.current,
      seq: seqRef.current,
      fromIndex: fromIndexRef.current,
      append: [...pendingAppendRef.current],
    };

    fromIndexRef.current += pendingAppendRef.current.length;
    pendingAppendRef.current = [];
    lastUpdateSentRef.current = Date.now();

    wsService.send({
      type: 'DRAW_UPDATE',
      payload: deltaPayload,
    });
  }, [wsService]);

  const addPoint = useCallback(
    (coord: Coordinate) => {
      if (!isDrawingRef.current) return;

      const last = pointsRef.current[pointsRef.current.length - 1];
      if (last && Math.abs(last.lat - coord.lat) < 1e-6 && Math.abs(last.lng - coord.lng) < 1e-6) {
        return; // Ignore duplicate vertex click
      }

      const next = [...pointsRef.current, coord];
      pointsRef.current = next;

      // Send DRAW_START on first point
      if (next.length === 1 && shapeIdRef.current) {
        wsService.send({
          type: 'DRAW_START',
          payload: { shapeId: shapeIdRef.current, point: coord },
        });
        fromIndexRef.current = 1;
      } else {
        // Buffer vertex delta for throttled DRAW_UPDATE with trailing edge
        pendingAppendRef.current.push(coord);
        const now = Date.now();
        const elapsed = now - lastUpdateSentRef.current;
        if (elapsed >= 66) {
          if (throttleTimerRef.current) {
            clearTimeout(throttleTimerRef.current);
            throttleTimerRef.current = null;
          }
          flushDeltaUpdate();
        } else if (!throttleTimerRef.current) {
          throttleTimerRef.current = setTimeout(() => {
            throttleTimerRef.current = null;
            flushDeltaUpdate();
          }, 66 - elapsed);
        }
      }

      setPoints(next);
    },
    [wsService, flushDeltaUpdate]
  );

  const updateCursorPoint = useCallback(
    (coord: Coordinate | null) => {
      if (!isDrawingRef.current) return;
      setCursorPoint(coord);
    },
    []
  );

  const finishDrawing = useCallback(() => {
    if (!isDrawingRef.current) return;

    flushDeltaUpdate();

    const clean = removeDuplicateConsecutive(pointsRef.current);
    const validation = validatePolygonCoordinates(clean);

    if (!validation.valid) {
      setValidationError(validation.reason || 'Invalid polygon geometry');
      return;
    }

    setValidationError(null);
    isDrawingRef.current = false;
    setIsDrawing(false);
    setCursorPoint(null);
    setIsSaveModalOpen(true);

    if (options?.onPolygonCreated) {
      options.onPolygonCreated(clean);
    }
  }, [flushDeltaUpdate, options]);

  const cancelDrawing = useCallback(() => {
    if (throttleTimerRef.current) {
      clearTimeout(throttleTimerRef.current);
      throttleTimerRef.current = null;
    }
    if (pendingCommitRef.current) {
      clearTimeout(pendingCommitRef.current.timeoutId);
      pendingCommitRef.current.reject(new Error('Drawing cancelled'));
      pendingCommitRef.current = null;
    }
    if (shapeIdRef.current) {
      wsService.send({
        type: 'DRAW_CANCEL',
        payload: { shapeId: shapeIdRef.current },
      });
    }

    shapeIdRef.current = null;
    seqRef.current = 0;
    pendingAppendRef.current = [];
    isDrawingRef.current = false;
    pointsRef.current = [];
    setIsDrawing(false);
    setPoints([]);
    setCursorPoint(null);
    setValidationError(null);
    setIsSaveModalOpen(false);
  }, [wsService]);

  const saveDrawing = useCallback(
    async (name: string) => {
      const clean = removeDuplicateConsecutive(points);
      if (clean.length < 3) return;

      const currentShapeId = shapeIdRef.current || undefined;

      // In connected mode: emit DRAW_COMMIT over WebSocket, which creates the area
      // and broadcasts AREA_SAVED with shapeId (HLD §9.1)
      // In degraded/polling mode: persist directly via HTTP POST (Task 8 / HLD §12.1)
      if (wsService.connectionState === 'connected' && currentShapeId) {
        return new Promise<Area | void>((resolve, reject) => {
          const timeoutId = setTimeout(async () => {
            if (pendingCommitRef.current?.shapeId === currentShapeId) {
              pendingCommitRef.current = null;
              // On WS timeout, attempt HTTP fallback
              try {
                const area = await createArea(name, clean, currentShapeId);
                setIsSaveModalOpen(false);
                isDrawingRef.current = false;
                setIsDrawing(false);
                setPoints([]);
                shapeIdRef.current = null;
                resolve(area);
              } catch (fallbackErr) {
                reject(
                  fallbackErr instanceof Error
                    ? fallbackErr
                    : new Error('Save timed out. Please try again.')
                );
              }
            }
          }, 5000);

          pendingCommitRef.current = {
            shapeId: currentShapeId,
            resolve,
            reject,
            timeoutId,
          };

          wsService.send({
            type: 'DRAW_COMMIT',
            payload: {
              shapeId: currentShapeId,
              name,
              points: clean,
            },
          });
        });
      } else {
        const createdArea = await createArea(name, clean, currentShapeId);
        setIsSaveModalOpen(false);
        isDrawingRef.current = false;
        setIsDrawing(false);
        setPoints([]);
        shapeIdRef.current = null;
        return createdArea;
      }
    },
    [points, createArea, wsService]
  );

  // If an AREA_SAVED arrives with local shapeId, replace local preview with saved area
  useEffect(() => {
    const unsubSaved = wsService.on('AREA_SAVED', (payload) => {
      if (payload.shapeId && payload.shapeId === shapeIdRef.current) {
        if (pendingCommitRef.current?.shapeId === payload.shapeId) {
          clearTimeout(pendingCommitRef.current.timeoutId);
          pendingCommitRef.current.resolve(payload.area);
          pendingCommitRef.current = null;
        }
        shapeIdRef.current = null;
        isDrawingRef.current = false;
        setIsDrawing(false);
        setPoints([]);
        setIsSaveModalOpen(false);
        selectArea(payload.area.id);
      }
    });

    const unsubError = wsService.on('ERROR', (payload) => {
      if (pendingCommitRef.current) {
        clearTimeout(pendingCommitRef.current.timeoutId);
        const errMsg = payload.message || payload.code || 'Failed to save area';
        pendingCommitRef.current.reject(new Error(errMsg));
        pendingCommitRef.current = null;
      }
    });

    return () => {
      unsubSaved();
      unsubError();
    };
  }, [wsService, selectArea]);

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      if (throttleTimerRef.current) {
        clearTimeout(throttleTimerRef.current);
        throttleTimerRef.current = null;
      }
      if (pendingCommitRef.current) {
        clearTimeout(pendingCommitRef.current.timeoutId);
        pendingCommitRef.current = null;
      }
    };
  }, []);

  // Keyboard shortcut listener: Enter to finish, Escape to cancel
  useEffect(() => {
    if (!isDrawing) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        finishDrawing();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        cancelDrawing();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isDrawing, finishDrawing, cancelDrawing]);

  return {
    isDrawing,
    points,
    cursorPoint,
    approxAreaKm2,
    formattedApproxArea,
    validationError,
    isSaveModalOpen,
    startDrawing,
    addPoint,
    updateCursorPoint,
    finishDrawing,
    cancelDrawing,
    saveDrawing,
    setIsSaveModalOpen,
  };
}
