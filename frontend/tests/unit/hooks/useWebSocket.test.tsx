import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from '../../../src/hooks/useWebSocket';
import { ApiProvider } from '../../../src/providers/ApiProvider';
import { MockWebSocketService } from '../../../src/api/mock/mockWebSocketService';
import { MockAuthApi } from '../../../src/api/mock/mockAuthApi';

describe('useWebSocket', () => {
  let mockWsService: MockWebSocketService;
  let mockAuthApi: MockAuthApi;

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <ApiProvider wsService={mockWsService} authApi={mockAuthApi}>
      {children}
    </ApiProvider>
  );

  beforeEach(() => {
    vi.useFakeTimers();
    mockWsService = new MockWebSocketService();
    mockAuthApi = new MockAuthApi();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects and receives presence snapshot deterministically', async () => {
    const { result } = renderHook(() => useWebSocket(true), { wrapper });

    // Advance fake timers to resolve mock ticket acquisition and connect delay
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(result.current.connectionState).toBe('connected');
    expect(result.current.presenceUsers.length).toBeGreaterThan(0);
  });

  it('throttles cursor movements to max 10 Hz and permits movements after 100ms window', async () => {
    const { result } = renderHook(() => useWebSocket(false), { wrapper });

    act(() => {
      result.current.sendCursorMove({ lat: 32.0, lng: 34.8 });
      result.current.sendCursorMove({ lat: 32.01, lng: 34.81 });
      result.current.sendCursorMove({ lat: 32.02, lng: 34.82 });
    });

    let cursorMessages = mockWsService.sentMessages.filter((m) => m.type === 'CURSOR_MOVE');
    expect(cursorMessages).toHaveLength(1);
    expect(cursorMessages[0].payload).toEqual({ lat: 32.0, lng: 34.8 });

    // Advance time past 100ms throttle interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(150);
    });

    act(() => {
      result.current.sendCursorMove({ lat: 32.05, lng: 34.85 });
    });

    cursorMessages = mockWsService.sentMessages.filter((m) => m.type === 'CURSOR_MOVE');
    expect(cursorMessages).toHaveLength(2);
    expect(cursorMessages[1].payload).toEqual({ lat: 32.05, lng: 34.85 });
  });
});
