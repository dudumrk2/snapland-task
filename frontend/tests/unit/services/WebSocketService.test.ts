import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WebSocketService } from '../../../src/services/websocket/WebSocketService';
import type { ConnectionState } from '../../../src/api/interfaces/IWebSocketService';

class MockNativeWebSocket {
  static instances: MockNativeWebSocket[] = [];
  url: string;
  readyState: number = WebSocket.CONNECTING;
  sentMessages: string[] = [];

  onopen: ((event: any) => void) | null = null;
  onclose: ((event: any) => void) | null = null;
  onmessage: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockNativeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code = 1000, reason = '') {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code, reason });
    }
  }

  simulateOpen() {
    this.readyState = WebSocket.OPEN;
    if (this.onopen) {
      this.onopen({});
    }
  }

  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) });
    }
  }

  simulateError() {
    if (this.onerror) {
      this.onerror(new Error('Simulated WS Error'));
    }
  }
}

describe('WebSocketService (Real client)', () => {
  let wsService: WebSocketService;
  let originalWebSocket: any;

  beforeEach(() => {
    vi.useFakeTimers();
    MockNativeWebSocket.instances = [];
    originalWebSocket = (globalThis as any).WebSocket;
    (globalThis as any).WebSocket = MockNativeWebSocket;
    wsService = new WebSocketService('ws://localhost:8000/ws');
  });

  afterEach(() => {
    wsService.disconnect();
    (globalThis as any).WebSocket = originalWebSocket;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const flushAsync = async () => {
    await Promise.resolve();
    await Promise.resolve();
  };

  it('calls ticketProvider before EVERY connection attempt and connects to URL with ticket', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('fresh-ticket-1');

    wsService.connect(ticketProvider);
    await flushAsync();

    expect(ticketProvider).toHaveBeenCalledTimes(1);
    expect(MockNativeWebSocket.instances.length).toBe(1);
    expect(MockNativeWebSocket.instances[0].url).toContain('ticket=fresh-ticket-1');
  });

  it('unpacks micro-batch array frames and dispatches to registered on(type, handler) listeners', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('t1');
    wsService.connect(ticketProvider);
    await flushAsync();

    const socket = MockNativeWebSocket.instances[0];
    socket.simulateOpen();

    const cursorHandler = vi.fn();
    const areaSavedHandler = vi.fn();

    wsService.on('CURSOR_MOVE', cursorHandler);
    wsService.on('AREA_SAVED', areaSavedHandler);

    // Backend micro-batch frame: an array of 2 messages
    const frame = [
      {
        type: 'CURSOR_MOVE',
        payload: { userId: 'u2', lat: 32.1, lng: 34.8 },
      },
      {
        type: 'AREA_SAVED',
        eventId: 'stream-evt-100',
        payload: {
          area: {
            id: 'area-1',
            name: 'New Area',
            coordinates: [],
            areaKm2: 1.0,
            version: 1,
            createdBy: 'u1',
            lastEditedBy: 'u1',
            createdAt: '2026-10-01',
            updatedAt: '2026-10-01',
          },
          shapeId: 'shape-abc',
        },
      },
    ];

    socket.simulateMessage(frame);

    expect(cursorHandler).toHaveBeenCalledWith(
      { userId: 'u2', lat: 32.1, lng: 34.8 },
      undefined
    );
    expect(areaSavedHandler).toHaveBeenCalledWith(
      frame[1].payload,
      'stream-evt-100'
    );
    expect(wsService.lastEventId).toBe('stream-evt-100');
  });

  it('appends lastEventId to URL on subsequent reconnects', async () => {
    let ticketCounter = 1;
    const ticketProvider = vi.fn().mockImplementation(async () => `ticket-${ticketCounter++}`);

    wsService.connect(ticketProvider);
    await flushAsync();

    const socket1 = MockNativeWebSocket.instances[0];
    socket1.simulateOpen();

    // Receive message carrying durable eventId
    socket1.simulateMessage([
      {
        type: 'AREA_UPDATED',
        eventId: '1727500000-0',
        payload: { area: { id: 'a1', version: 2 } },
      },
    ]);

    expect(wsService.lastEventId).toBe('1727500000-0');

    // Simulate unexpected disconnect
    socket1.close(1006, 'Abnormal closure');

    // Advance timer past backoff delay
    await vi.advanceTimersByTimeAsync(2000);

    expect(MockNativeWebSocket.instances.length).toBe(2);
    expect(MockNativeWebSocket.instances[1].url).toContain('ticket=ticket-2');
    expect(MockNativeWebSocket.instances[1].url).toContain('lastEventId=1727500000-0');
  });

  it('reconnects immediately with fresh ticket on code 4401 (token expiry) without failure increment', async () => {
    let ticketCounter = 1;
    const ticketProvider = vi.fn().mockImplementation(async () => `ticket-${ticketCounter++}`);

    wsService.connect(ticketProvider);
    await flushAsync();

    const socket = MockNativeWebSocket.instances[0];
    socket.simulateOpen();
    expect(wsService.connectionState).toBe('connected');

    // Server closes after 15 min with code 4401
    socket.close(4401, 'Token expired');

    // Immediate reconnect without backoff (after 100ms debounce)
    await vi.advanceTimersByTimeAsync(150);
    await flushAsync();

    expect(ticketProvider).toHaveBeenCalledTimes(2);
    expect(MockNativeWebSocket.instances.length).toBe(2);
    expect(MockNativeWebSocket.instances[1].url).toContain('ticket=ticket-2');
    // Does not count as a failure
    expect((wsService as any).consecutiveFailures).toBe(0);
  });

  it('applies exponential backoff if code 4401 occurs repeatedly (>2 times)', async () => {
    let ticketCounter = 1;
    const ticketProvider = vi.fn().mockImplementation(async () => `ticket-${ticketCounter++}`);

    wsService.connect(ticketProvider);
    await flushAsync();

    // 1st 4401 -> 100ms debounce
    MockNativeWebSocket.instances[0].close(4401, 'Token expired');
    await vi.advanceTimersByTimeAsync(150);
    await flushAsync();
    expect(MockNativeWebSocket.instances.length).toBe(2);

    // 2nd 4401 -> 100ms debounce
    MockNativeWebSocket.instances[1].close(4401, 'Token expired');
    await vi.advanceTimersByTimeAsync(150);
    await flushAsync();
    expect(MockNativeWebSocket.instances.length).toBe(3);

    // 3rd 4401 -> now exceeds 2, delegates to handleConnectionFailure
    MockNativeWebSocket.instances[2].close(4401, 'Token expired');
    expect((wsService as any).consecutiveFailures).toBe(1);
    expect(wsService.connectionState).toBe('reconnecting');
  });

  it('transitions connectionState to polling after 5 consecutive failures and retries every 30s', async () => {
    const states: ConnectionState[] = [];
    wsService.onStateChange((s) => states.push(s));

    const ticketProvider = vi.fn().mockResolvedValue('retry-ticket');
    wsService.connect(ticketProvider);
    await flushAsync();

    // 4 initial failures
    for (let i = 0; i < 4; i++) {
      const currentSocket = MockNativeWebSocket.instances[MockNativeWebSocket.instances.length - 1];
      currentSocket.close(1006, 'Failure');
      await vi.advanceTimersByTimeAsync(20000);
      await flushAsync();
    }

    // 5th failure
    const fifthSocket = MockNativeWebSocket.instances[MockNativeWebSocket.instances.length - 1];
    fifthSocket.close(1006, 'Failure');

    expect(wsService.connectionState).toBe('polling');
    expect(states).toContain('polling');

    // While in polling, socket is retried every 30s
    const countBefore = MockNativeWebSocket.instances.length;
    await vi.advanceTimersByTimeAsync(30000);
    await flushAsync();
    expect(MockNativeWebSocket.instances.length).toBeGreaterThan(countBefore);
  });

  it('dispatches snapland:resync_viewport event when RESYNC_REQUIRED arrives', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('t-resync');
    wsService.connect(ticketProvider);
    await flushAsync();

    const socket = MockNativeWebSocket.instances[0];
    socket.simulateOpen();

    const resyncListener = vi.fn();
    window.addEventListener('snapland:resync_viewport', resyncListener);

    socket.simulateMessage([
      {
        type: 'RESYNC_REQUIRED',
        payload: { reason: 'stream_trimmed' },
      },
    ]);

    expect(resyncListener).toHaveBeenCalled();
    window.removeEventListener('snapland:resync_viewport', resyncListener);
  });

  it('dispatches snapland:toast notification when ERROR with RATE_LIMITED arrives', async () => {
    const ticketProvider = vi.fn().mockResolvedValue('t-err');
    wsService.connect(ticketProvider);
    await flushAsync();

    const socket = MockNativeWebSocket.instances[0];
    socket.simulateOpen();

    const toastListener = vi.fn();
    window.addEventListener('snapland:toast', toastListener);

    socket.simulateMessage([
      {
        type: 'ERROR',
        payload: { code: 'RATE_LIMITED', retryAfterMs: 15000 },
      },
    ]);

    expect(toastListener).toHaveBeenCalled();
    const event = toastListener.mock.calls[0][0] as CustomEvent;
    expect(event.detail.message).toContain('15s');

    window.removeEventListener('snapland:toast', toastListener);
  });
});
