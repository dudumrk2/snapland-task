import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDrawing } from '../../../src/hooks/useDrawing';
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

    expect(result.current.validationError).toBeDefined();
    expect(result.current.isSaveModalOpen).toBe(false);
  });
});
