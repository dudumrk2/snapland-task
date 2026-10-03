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

export const COMMIT_TIMEOUT_MS = 8000;

export class DrawingAbortedError extends Error {
  constructor(message: string = 'Drawing was aborted') {
    super(message);
    this.name = 'DrawingAbortedError';
  }
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
  const submittedShapeIdsRef = useRef<Set<string>>(new Set());
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
  const isSavingRef = useRef<boolean>(false);
  const isMountedRef = useRef<boolean>(true);
  const optionsRef = useRef(options);
  optionsRef.current = options;

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
    submittedShapeIdsRef.current.clear();
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

    if (optionsRef.current?.onPolygonCreated) {
      optionsRef.current.onPolygonCreated(clean);
    }
  }, [flushDeltaUpdate]);

  const cancelDrawing = useCallback(() => {
    // If a commit is in flight, do not cancel while server is processing it
    if (isSavingRef.current || pendingCommitRef.current) {
      return;
    }

    if (throttleTimerRef.current) {
      clearTimeout(throttleTimerRef.current);
      throttleTimerRef.current = null;
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
      if (isSavingRef.current || pendingCommitRef.current) {
        throw new Error('Save already in progress');
      }

      const clean = removeDuplicateConsecutive(points);
      if (clean.length < 3) {
        throw new Error('Insufficient vertices to save polygon');
      }

      isSavingRef.current = true;
      const currentShapeId = shapeIdRef.current || undefined;

      // In connected mode: emit DRAW_COMMIT over WebSocket, which creates the area
      // and broadcasts AREA_SAVED with shapeId (HLD §9.1)
      // In degraded/polling mode: persist directly via HTTP POST (Task 8 / HLD §12.1)
      if (wsService.connectionState === 'connected' && currentShapeId) {
        submittedShapeIdsRef.current.add(currentShapeId);
        return new Promise<Area | void>((resolve, reject) => {
          const timeoutId = setTimeout(() => {
            if (pendingCommitRef.current?.shapeId === currentShapeId) {
              pendingCommitRef.current = null;
              isSavingRef.current = false;
              reject(new Error('Save timed out. Please try again.'));
            }
          }, COMMIT_TIMEOUT_MS);

          pendingCommitRef.current = {
            shapeId: currentShapeId,
            resolve: (area) => {
              isSavingRef.current = false;
              resolve(area);
            },
            reject: (err) => {
              isSavingRef.current = false;
              reject(err);
            },
            timeoutId,
          };

          const sent = wsService.send({
            type: 'DRAW_COMMIT',
            payload: {
              shapeId: currentShapeId,
              name,
              points: clean,
            },
          });

          if (sent === false) {
            clearTimeout(timeoutId);
            pendingCommitRef.current = null;
            // Socket was not OPEN; fall back to HTTP createArea
            createArea(name, clean, currentShapeId)
              .then((createdArea) => {
                isSavingRef.current = false;
                if (!isMountedRef.current) {
                  reject(new DrawingAbortedError('Component unmounted'));
                  return;
                }
                setIsSaveModalOpen(false);
                isDrawingRef.current = false;
                setIsDrawing(false);
                setPoints([]);
                shapeIdRef.current = null;
                submittedShapeIdsRef.current.clear();
                resolve(createdArea);
              })
              .catch((err) => {
                isSavingRef.current = false;
                reject(err);
              });
          }
        });
      } else {
        try {
          const createdArea = await createArea(name, clean, currentShapeId);
          if (!isMountedRef.current) {
            throw new DrawingAbortedError('Component unmounted');
          }
          setIsSaveModalOpen(false);
          isDrawingRef.current = false;
          setIsDrawing(false);
          setPoints([]);
          shapeIdRef.current = null;
          submittedShapeIdsRef.current.clear();
          return createdArea;
        } finally {
          isSavingRef.current = false;
        }
      }
    },
    [points, createArea, wsService]
  );

  // If an AREA_SAVED arrives with local shapeId, replace local preview with saved area
  useEffect(() => {
    const unsubSaved = wsService.on('AREA_SAVED', (payload) => {
      const isCurrentShape = payload.shapeId && payload.shapeId === shapeIdRef.current;
      const isSubmittedShape = payload.shapeId && submittedShapeIdsRef.current.has(payload.shapeId);

      if (isCurrentShape || isSubmittedShape) {
        const pending = pendingCommitRef.current;
        if (pending && pending.shapeId === payload.shapeId) {
          clearTimeout(pending.timeoutId);
          pending.resolve(payload.area);
          pendingCommitRef.current = null;
        }
        shapeIdRef.current = null;
        submittedShapeIdsRef.current.clear();
        if (isMountedRef.current) {
          isDrawingRef.current = false;
          setIsDrawing(false);
          setPoints([]);
          setIsSaveModalOpen(false);
          selectArea(payload.area.id);
        }
      }
    });

    const unsubError = wsService.on('ERROR', (payload) => {
      if (pendingCommitRef.current) {
        // If error specifies a shapeId, ignore if it belongs to a different shape
        if (payload.shapeId && payload.shapeId !== pendingCommitRef.current.shapeId) {
          return;
        }
        // If error specifies refType that is NOT DRAW_COMMIT, ignore (e.g. rate limit on cursor or delta)
        if (payload.refType && payload.refType !== 'DRAW_COMMIT') {
          return;
        }

        clearTimeout(pendingCommitRef.current.timeoutId);
        let errMsg = payload.message || payload.code || 'Failed to save area';
        if (payload.code === 'RATE_LIMITED') {
          const retrySec = payload.retryAfterMs ? Math.ceil(payload.retryAfterMs / 1000) : 1;
          errMsg = payload.message || `Rate limited. Please retry in ${retrySec}s.`;
        }
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
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (throttleTimerRef.current) {
        clearTimeout(throttleTimerRef.current);
        throttleTimerRef.current = null;
      }
      if (pendingCommitRef.current) {
        clearTimeout(pendingCommitRef.current.timeoutId);
        pendingCommitRef.current.reject(new DrawingAbortedError('Component unmounted'));
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
        if (!pendingCommitRef.current) {
          e.preventDefault();
          cancelDrawing();
        }
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
