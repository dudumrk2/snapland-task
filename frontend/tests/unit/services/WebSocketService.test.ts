import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { RealWebSocketService } from '../../../src/services/websocket/WebSocketService';

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];
  readyState = MockWebSocket.OPEN;
  url: string;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason: string }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((err: unknown) => void) | null = null;
  sentData: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      if (this.onopen && this.readyState !== MockWebSocket.CLOSED) this.onopen();
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
    MockWebSocket.instances = [];
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
      // Advance timers until backoff timer fires and reconnect completes (bounded to 200 ticks = 40s)
      let iterations = 0;
      while (wsService.connectionState !== 'connected' && iterations < 200) {
        await vi.advanceTimersByTimeAsync(200);
        iterations++;
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

  it('handles React 18 StrictMode quick remount (connect -> disconnect -> connect) cleanly without orphan reconnection', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('strictmode-ticket');

    // First mount connects
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(10);
    expect(MockWebSocket.instances).toHaveLength(1);

    // Unmount disconnects
    wsService.disconnect();
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED);

    // Second mount connects
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(50);
    expect(wsService.connectionState).toBe('connected');

    // Advancing time should not fire any stray reconnect timer or disconnect the active socket
    await vi.advanceTimersByTimeAsync(5000);
    expect(wsService.connectionState).toBe('connected');

    // Verify only 2 instances were created, first is closed, second is currently open
    expect(MockWebSocket.instances).toHaveLength(2);
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED);
    expect(MockWebSocket.instances[1].readyState).toBe(MockWebSocket.OPEN);
    expect((wsService as unknown as { socket: MockWebSocket }).socket).toBe(MockWebSocket.instances[1]);
  });

  it('does not reset failure counter on early message arrival until stability window passes', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('stability-ticket');

    // Induce failures first
    const failProvider = vi.fn().mockRejectedValue(new Error('fail'));
    wsService.connect(failProvider);
    await vi.advanceTimersByTimeAsync(1500); // failure 1
    await vi.advanceTimersByTimeAsync(2500); // failure 2
    const initialFailures = (wsService as unknown as { consecutiveFailures: number }).consecutiveFailures;
    expect(initialFailures).toBeGreaterThanOrEqual(2);
    expect(wsService.connectionState).toBe('reconnecting');

    // Now connect successfully with ticketProvider
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('connected');

    // Receive message immediately (e.g. PRESENCE_SNAPSHOT)
    const socket = (wsService as unknown as { socket: MockWebSocket }).socket;
    socket.onmessage?.({
      data: JSON.stringify([{ type: 'PRESENCE_SNAPSHOT', payload: { users: [] } }]),
    });

    // Close before 10s stability window
    socket.close(1006, 'Drop');
    await vi.advanceTimersByTimeAsync(10);

    // Because stability window was not reached, consecutiveFailures was not cleared!
    // It should have incremented beyond initialFailures (not reset to 1)
    const finalFailures = (wsService as unknown as { consecutiveFailures: number }).consecutiveFailures;
    expect(finalFailures).toBe(initialFailures + 1);
    expect(wsService.connectionState).toBe('reconnecting');
  });

  it('updates state to reconnecting immediately on 4401 close', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('ticket-4401');
    wsService.connect(ticketProvider);
    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('connected');

    const stateChanges: string[] = [];
    wsService.onStateChange((st) => stateChanges.push(st));

    const socket = (wsService as unknown as { socket: MockWebSocket }).socket;
    socket.close(4401, 'Token expired');

    expect(wsService.connectionState).toBe('reconnecting');
    expect(stateChanges).toContain('reconnecting');

    await vi.advanceTimersByTimeAsync(10);
    expect(wsService.connectionState).toBe('connected');
  });
});
