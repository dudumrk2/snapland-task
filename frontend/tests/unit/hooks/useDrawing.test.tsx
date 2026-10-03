import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDrawing, COMMIT_TIMEOUT_MS } from '../../../src/hooks/useDrawing';
import { ApiProvider } from '../../../src/providers/ApiProvider';
import { MockAreaApi } from '../../../src/api/mock/mockAreaApi';
import { MockWebSocketService } from '../../../src/api/mock/mockWebSocketService';

describe('useDrawing', () => {
  let mockAreaApi: MockAreaApi;
  let mockWsService: MockWebSocketService;

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ApiProvider areaApi={mockAreaApi} wsService={mockWsService}>
      {children}
    </ApiProvider>
  );

  beforeEach(() => {
    mockAreaApi = new MockAreaApi([]);
    mockWsService = new MockWebSocketService();
  });

  it('starts in non-drawing idle state', () => {
    const { result } = renderHook(() => useDrawing(), { wrapper });
    expect(result.current.isDrawing).toBe(false);
    expect(result.current.points).toHaveLength(0);
    expect(result.current.approxAreaKm2).toBe(0);
  });

  it('starts drawing and appends distinct vertices', () => {
    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
    });
    expect(result.current.isDrawing).toBe(true);

    act(() => {
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
    });
    expect(result.current.points).toHaveLength(1);

    // Duplicate vertex is ignored
    act(() => {
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
    });
    expect(result.current.points).toHaveLength(1);

    act(() => {
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
    });
    expect(result.current.points).toHaveLength(3);
    expect(result.current.approxAreaKm2).toBeGreaterThan(0);
  });

  it('cancels drawing and resets points', () => {
    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.cancelDrawing();
    });

    expect(result.current.isDrawing).toBe(false);
    expect(result.current.points).toHaveLength(0);
  });

  it('opens save modal on valid polygon finish', () => {
    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    expect(result.current.validationError).toBeNull();
    expect(result.current.isSaveModalOpen).toBe(true);
  });

  it('rejects finish with fewer than 3 vertices', () => {
    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.finishDrawing();
    });

    expect(result.current.validationError).not.toBeNull();
    expect(result.current.isSaveModalOpen).toBe(false);
  });

  it('keeps points and modal open when HTTP save fails', async () => {
    mockAreaApi.createArea = vi.fn().mockRejectedValue(new Error('Validation failed: self intersection'));

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    expect(result.current.isSaveModalOpen).toBe(true);
    expect(result.current.points).toHaveLength(3);

    // Attempt save which fails
    await act(async () => {
      await expect(result.current.saveDrawing('Failed Area')).rejects.toThrow('Validation failed: self intersection');
    });

    // Points and modal must remain preserved
    expect(result.current.points).toHaveLength(3);
    expect(result.current.isSaveModalOpen).toBe(true);
  });

  it('flushes trailing DRAW_UPDATE after throttle timeout when user pauses', () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useDrawing(), { wrapper });

      act(() => {
        result.current.startDrawing();
        // First point sends DRAW_START
        result.current.addPoint({ lat: 32.0, lng: 34.8 });
      });

      expect(mockWsService.sentMessages).toHaveLength(1);
      expect(mockWsService.sentMessages[0].type).toBe('DRAW_START');

      // Add point 2 - this will send the first DRAW_UPDATE immediately (elapsed from 0 is > 66ms)
      act(() => {
        result.current.addPoint({ lat: 32.0, lng: 34.9 });
      });

      const initialDrawUpdates = mockWsService.sentMessages.filter((m) => m.type === 'DRAW_UPDATE');
      expect(initialDrawUpdates).toHaveLength(1);

      // Add point 3 immediately within 66ms window (< 66ms elapsed)
      act(() => {
        result.current.addPoint({ lat: 32.05, lng: 34.95 });
      });

      // Point 3 must be buffered in pendingAppendRef and not yet sent
      expect(mockWsService.sentMessages.filter((m) => m.type === 'DRAW_UPDATE')).toHaveLength(1);

      // Advance timers by 70ms to fire trailing throttle flush
      act(() => {
        vi.advanceTimersByTime(70);
      });

      // Second DRAW_UPDATE must now be sent
      const finalDrawUpdates = mockWsService.sentMessages.filter((m) => m.type === 'DRAW_UPDATE');
      expect(finalDrawUpdates).toHaveLength(2);
      expect(
        (finalDrawUpdates[1].payload as { append: Array<{ lat: number; lng: number }> }).append
      ).toEqual([{ lat: 32.05, lng: 34.95 }]);
    } finally {
      vi.useRealTimers();
    }
  });

  it('preserves points and rejects saveDrawing when WebSocket ERROR arrives', async () => {
    // Connect mock WebSocket service and wait for connection
    mockWsService.connect(async () => 'ticket');
    await new Promise((r) => setTimeout(r, 150));
    expect(mockWsService.connectionState).toBe('connected');

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    expect(result.current.points).toHaveLength(3);

    // Prevent MockWebSocketService from automatically dispatching AREA_SAVED
    vi.spyOn(mockWsService, 'send').mockImplementation((msg) => {
      mockWsService.sentMessages.push(msg);
      return true;
    });

    // Call saveDrawing
    let savePromise: Promise<unknown>;
    act(() => {
      savePromise = result.current.saveDrawing('Polygon With Error');
    });

    // Simulate backend sending ERROR
    act(() => {
      mockWsService.dispatch('ERROR', {
        code: 'VALIDATION_ERROR',
        message: 'Polygon geometry intersects itself',
      });
    });

    await expect(savePromise!).rejects.toThrow('Polygon geometry intersects itself');
    // Points must remain intact
    expect(result.current.points).toHaveLength(3);
    expect(result.current.isSaveModalOpen).toBe(true);
  });

  it('rejects saveDrawing immediately when RATE_LIMITED error arrives', async () => {
    mockWsService.connect(async () => 'ticket');
    await new Promise((r) => setTimeout(r, 150));

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    vi.spyOn(mockWsService, 'send').mockImplementation((msg) => {
      mockWsService.sentMessages.push(msg);
      return true;
    });

    let savePromise: Promise<unknown>;
    act(() => {
      savePromise = result.current.saveDrawing('Polygon With Rate Limit');
    });

    // Dispatch RATE_LIMITED error
    act(() => {
      mockWsService.dispatch('ERROR', {
        code: 'RATE_LIMITED',
        message: 'Too many drawing actions',
        retryAfterMs: 3000,
      });
    });

    await expect(savePromise!).rejects.toThrow('Too many drawing actions');
    expect(result.current.isSaveModalOpen).toBe(true);
    expect(result.current.points).toHaveLength(3);
  });

  it('ignores ERROR meant for a different shapeId and resolves on AREA_SAVED', async () => {
    mockWsService.connect(async () => 'ticket');
    await new Promise((r) => setTimeout(r, 150));

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    vi.spyOn(mockWsService, 'send').mockImplementation((msg) => {
      mockWsService.sentMessages.push(msg);
      return true;
    });

    let savePromise: Promise<unknown>;
    act(() => {
      savePromise = result.current.saveDrawing('Polygon With Unrelated Error');
    });

    // Dispatch ERROR for a different shapeId
    act(() => {
      mockWsService.dispatch('ERROR', {
        code: 'VALIDATION_ERROR',
        message: 'Other shape invalid',
        shapeId: 'different-shape-id-999',
      });
    });

    // Now dispatch AREA_SAVED with the active shapeId
    const activeShapeId = (mockWsService.sentMessages.find((m) => m.type === 'DRAW_COMMIT')?.payload as { shapeId: string }).shapeId;
    act(() => {
      mockWsService.dispatch('AREA_SAVED', {
        shapeId: activeShapeId,
        area: {
          id: 'area-123',
          name: 'Polygon With Unrelated Error',
          coordinates: result.current.points,
          areaKm2: 1.5,
          version: 1,
          createdBy: 'user-1',
          lastEditedBy: 'user-1',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      });
    });

    await expect(savePromise!).resolves.toBeDefined();
    expect(result.current.isSaveModalOpen).toBe(false);
    expect(result.current.points).toHaveLength(0);
  });

  it('falls back to HTTP createArea when wsService.send returns false', async () => {
    mockWsService.connect(async () => 'ticket');
    await new Promise((r) => setTimeout(r, 150));

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    // wsService.send returns false (socket closing or not ready)
    vi.spyOn(mockWsService, 'send').mockReturnValue(false);
    const createAreaSpy = vi.spyOn(mockAreaApi, 'createArea');

    let savedArea: unknown;
    await act(async () => {
      savedArea = await result.current.saveDrawing('HTTP Fallback Area');
    });

    expect(createAreaSpy).toHaveBeenCalled();
    expect(savedArea).toBeDefined();
    expect(result.current.isSaveModalOpen).toBe(false);
    expect(result.current.points).toHaveLength(0);
  });

  it('rejects saveDrawing with timeout error after 8s and preserves points', async () => {
    vi.useFakeTimers();
    try {
      mockWsService.connect(async () => 'ticket');
      // Advance to allow connect to complete
      await vi.advanceTimersByTimeAsync(150);
      expect(mockWsService.connectionState).toBe('connected');

      const { result } = renderHook(() => useDrawing(), { wrapper });

      act(() => {
        result.current.startDrawing();
        result.current.addPoint({ lat: 32.0, lng: 34.8 });
        result.current.addPoint({ lat: 32.0, lng: 34.9 });
        result.current.addPoint({ lat: 32.1, lng: 34.85 });
        result.current.finishDrawing();
      });

      vi.spyOn(mockWsService, 'send').mockImplementation((msg) => {
        mockWsService.sentMessages.push(msg);
        return true;
      });

      let savePromise: Promise<unknown>;
      act(() => {
        savePromise = result.current.saveDrawing('Timeout Area');
      });

      const assertion = expect(savePromise!).rejects.toThrow('Save timed out. Please try again.');

      // Advance timers by COMMIT_TIMEOUT_MS inside act
      await act(async () => {
        await vi.advanceTimersByTimeAsync(COMMIT_TIMEOUT_MS);
      });

      await assertion;
      expect(result.current.isSaveModalOpen).toBe(true);
      expect(result.current.points).toHaveLength(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('ignores RATE_LIMITED when refType is DRAW_UPDATE and allows saveDrawing to resolve', async () => {
    mockWsService.connect(async () => 'ticket');
    await new Promise((r) => setTimeout(r, 150));

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    vi.spyOn(mockWsService, 'send').mockImplementation((msg) => {
      mockWsService.sentMessages.push(msg);
      return true;
    });

    let savePromise: Promise<unknown>;
    act(() => {
      savePromise = result.current.saveDrawing('Polygon With Delta Rate Limit');
    });

    // Dispatch RATE_LIMITED specifically for a DRAW_UPDATE action
    act(() => {
      mockWsService.dispatch('ERROR', {
        code: 'RATE_LIMITED',
        message: 'Rate limit exceeded on DRAW_UPDATE',
        retryAfterMs: 1000,
        refType: 'DRAW_UPDATE',
      });
    });

    // Save promise should NOT be rejected by a DRAW_UPDATE rate limit!
    const activeShapeId = (mockWsService.sentMessages.find((m) => m.type === 'DRAW_COMMIT')?.payload as { shapeId: string }).shapeId;
    act(() => {
      mockWsService.dispatch('AREA_SAVED', {
        shapeId: activeShapeId,
        area: {
          id: 'area-delta-rl',
          name: 'Polygon With Delta Rate Limit',
          coordinates: result.current.points,
          areaKm2: 2.1,
          version: 1,
          createdBy: 'user-1',
          lastEditedBy: 'user-1',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      });
    });

    await expect(savePromise!).resolves.toBeDefined();
    expect(result.current.isSaveModalOpen).toBe(false);
    expect(result.current.points).toHaveLength(0);
  });

  it('rejects concurrent saveDrawing calls while a commit is in progress', async () => {
    mockWsService.connect(async () => 'ticket');
    await new Promise((r) => setTimeout(r, 150));

    const { result } = renderHook(() => useDrawing(), { wrapper });

    act(() => {
      result.current.startDrawing();
      result.current.addPoint({ lat: 32.0, lng: 34.8 });
      result.current.addPoint({ lat: 32.0, lng: 34.9 });
      result.current.addPoint({ lat: 32.1, lng: 34.85 });
      result.current.finishDrawing();
    });

    vi.spyOn(mockWsService, 'send').mockImplementation((msg) => {
      mockWsService.sentMessages.push(msg);
      return true;
    });

    let firstPromise: Promise<unknown>;
    act(() => {
      firstPromise = result.current.saveDrawing('First Save');
    });

    // Calling saveDrawing again immediately while first is in-flight
    await expect(result.current.saveDrawing('Second Save')).rejects.toThrow('Save already in progress');

    // Complete the first save
    const activeShapeId = (mockWsService.sentMessages.find((m) => m.type === 'DRAW_COMMIT')?.payload as { shapeId: string }).shapeId;
    act(() => {
      mockWsService.dispatch('AREA_SAVED', {
        shapeId: activeShapeId,
        area: {
          id: 'area-first',
          name: 'First Save',
          coordinates: [{ lat: 32.0, lng: 34.8 }],
          areaKm2: 1.0,
          version: 1,
          createdBy: 'user-1',
          lastEditedBy: 'user-1',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      });
    });

    await expect(firstPromise!).resolves.toBeDefined();
  });
});
