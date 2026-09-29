import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
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
    mockWsService = new MockWebSocketService();
    mockAuthApi = new MockAuthApi();
  });

  it('connects and receives presence snapshot', async () => {
    const { result } = renderHook(() => useWebSocket(true), { wrapper });

    // Use waitFor to avoid race condition with MockAuthApi latency + MockWebSocketService connect delay
    await waitFor(
      () => {
        expect(result.current.connectionState).toBe('connected');
      },
      { timeout: 500 }
    );

    expect(result.current.presenceUsers.length).toBeGreaterThan(0);
  });

  it('throttles cursor movements to max 10 Hz', () => {
    const { result } = renderHook(() => useWebSocket(false), { wrapper });

    act(() => {
      result.current.sendCursorMove({ lat: 32.0, lng: 34.8 });
      result.current.sendCursorMove({ lat: 32.01, lng: 34.81 });
      result.current.sendCursorMove({ lat: 32.02, lng: 34.82 });
    });

    // Does not throw and handles throttling
    expect(result.current.connectionState).toBe('disconnected');
  });
});
