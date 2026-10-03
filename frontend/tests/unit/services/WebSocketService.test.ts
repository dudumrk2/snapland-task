import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { RealWebSocketService } from '../../../src/services/websocket/WebSocketService';

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = MockWebSocket.OPEN;
  url: string;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((err: unknown) => void) | null = null;
  sentData: string[] = [];

  constructor(url: string) {
    this.url = url;
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 0);
  }

  send(data: string) {
    this.sentData.push(data);
  }

  close(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose({ code, reason });
  }
}

describe('RealWebSocketService', () => {
  let wsService: RealWebSocketService;
  let originalWebSocket: typeof WebSocket;

  beforeEach(() => {
    vi.useFakeTimers();
    originalWebSocket = globalThis.WebSocket;
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = MockWebSocket;
    wsService = new RealWebSocketService();
  });

  afterEach(() => {
    wsService.disconnect();
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = originalWebSocket;
    vi.useRealTimers();
  });

  it('connects using ticket and dispatches micro-batched frames', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('test-ticket-123');
    const stateSpy = vi.fn();
    wsService.onStateChange(stateSpy);

    wsService.connect(ticketProvider);
    expect(ticketProvider).toHaveBeenCalled();
    expect(wsService.connectionState).toBe('connecting');

    // Advance timer so mock websocket connects
    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('connected');

    const receivedEvents: string[] = [];
    wsService.on('AREA_SAVED', (payload, eventId) => {
      receivedEvents.push(`${payload.shapeId}:${eventId}`);
    });

    // Simulate micro-batch frame (array)
    const mockSocket = (wsService as unknown as { socket: MockWebSocket }).socket;
    mockSocket.onmessage?.({
      data: JSON.stringify([
        {
          type: 'AREA_SAVED',
          eventId: '1001-0',
          payload: {
            shapeId: 'shape-1',
            area: {
              id: 'a1',
              name: 'Area 1',
              coordinates: [{ lat: 32, lng: 34 }],
              area_km2: 1.5,
              version: 1,
              created_by: 'u1',
              last_edited_by: 'u1',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          },
        },
        {
          type: 'AREA_SAVED',
          eventId: '1002-0',
          payload: {
            shapeId: 'shape-2',
            area: {
              id: 'a2',
              name: 'Area 2',
              coordinates: [{ lat: 32, lng: 34 }],
              area_km2: 2.5,
              version: 1,
              created_by: 'u1',
              last_edited_by: 'u1',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          },
        },
      ]),
    });

    expect(receivedEvents).toEqual(['shape-1:1001-0', 'shape-2:1002-0']);
    expect(wsService.lastEventId).toBe('1002-0');
  });

  it('reconnects immediately on close code 4401 without incrementing failures', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('test-ticket-refresh');
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('connected');

    const mockSocket = (wsService as unknown as { socket: MockWebSocket }).socket;
    // Simulate close 4401
    mockSocket.close(4401, 'Token expired');

    // Should immediately attempt reconnect without counting failure
    await vi.advanceTimersByTimeAsync(10);
    expect(ticketProvider).toHaveBeenCalledTimes(2);
    expect(wsService.connectionState).toBe('connected');
  });

  it('transitions to polling after 5 consecutive failures', async () => {
    let callCount = 0;
    const ticketProvider = vi.fn().mockImplementation(() => {
      callCount++;
      return Promise.reject(new Error('Network error'));
    });

    wsService.connect(ticketProvider);

    // Failure 1: delay ~1s
    await vi.advanceTimersByTimeAsync(1500);
    // Failure 2: delay ~2s
    await vi.advanceTimersByTimeAsync(2500);
    // Failure 3: delay ~4s
    await vi.advanceTimersByTimeAsync(4500);
    // Failure 4: delay ~8s
    await vi.advanceTimersByTimeAsync(9000);
    // Failure 5: triggers state = 'polling'
    await vi.advanceTimersByTimeAsync(18000);

    expect(wsService.connectionState).toBe('polling');
  });

  it('triggers resync handler on RESYNC_REQUIRED', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('ticket');
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(10);

    const resyncSpy = vi.fn();
    wsService.onResync(resyncSpy);

    const mockSocket = (wsService as unknown as { socket: MockWebSocket }).socket;
    mockSocket.onmessage?.({
      data: JSON.stringify([{ type: 'RESYNC_REQUIRED', payload: {} }]),
    });

    expect(resyncSpy).toHaveBeenCalled();
  });

  it('repeated 4401 closes (>3) trigger connection failure backoff rather than infinite tight loop', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('test-ticket-repeat-4401');
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('connected');

    // Close with 4401 3 times without receiving messages (fast reconnects)
    for (let i = 0; i < 3; i++) {
      const socket = (wsService as unknown as { socket: MockWebSocket }).socket;
      socket.close(4401, 'Token expired');
      await vi.advanceTimersByTimeAsync(10);
      expect(wsService.connectionState).toBe('connected');
    }

    // 4th 4401 should trigger handleConnectionFailure (failure 1) -> reconnecting
    const socket4 = (wsService as unknown as { socket: MockWebSocket }).socket;
    socket4.close(4401, 'Token expired');
    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('reconnecting');

    // Simulate continuing failures without messages (failures 2, 3, 4, 5)
    // to verify consecutiveFailures escalates all the way to 'polling'
    for (let failCount = 2; failCount <= 5; failCount++) {
      // Advance timers until backoff timer fires and reconnect completes
      while (wsService.connectionState !== 'connected') {
        await vi.advanceTimersByTimeAsync(200);
      }
      expect(wsService.connectionState).toBe('connected');
      const s = (wsService as unknown as { socket: MockWebSocket }).socket;
      s.close(4401, 'Token expired');
      await vi.advanceTimersByTimeAsync(10);

      if (failCount < 5) {
        expect(wsService.connectionState).toBe('reconnecting');
      } else {
        // At 5th consecutive failure, state must transition to 'polling'
        expect(wsService.connectionState).toBe('polling');
      }
    }
  });
});
