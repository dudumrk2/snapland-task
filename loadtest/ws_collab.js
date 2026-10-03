import http from 'k6/http';
import { check, sleep } from 'k6';
import ws from 'k6/ws';
import { Counter, Gauge, Rate, Trend } from 'k6/metrics';

// Custom k6 metrics
const wsConnecting = new Trend('ws_connecting_duration', true);
const wsFanoutLatency = new Trend('ws_fanout_latency_ms', true);
const wsMessagesSent = new Counter('ws_messages_sent');
const wsMessagesReceived = new Counter('ws_messages_received');
const wsDroppedMessages = new Counter('ws_messages_dropped');
const wsActiveConnections = new Gauge('ws_active_connections');
const connectionSuccess = new Rate('connection_success_rate');

// Test configuration: scenarios of 50, 100, 200 users
export const options = {
  scenarios: {
    users_50: {
      executor: 'constant-vus',
      vus: 50,
      duration: '30s',
      startTime: '0s',
      tags: { scenario: '50_users' },
    },
    users_100: {
      executor: 'constant-vus',
      vus: 100,
      duration: '30s',
      startTime: '35s',
      tags: { scenario: '100_users' },
    },
    users_200: {
      executor: 'constant-vus',
      vus: 200,
      duration: '30s',
      startTime: '70s',
      tags: { scenario: '200_users' },
    },
  },
  thresholds: {
    connection_success_rate: ['rate>0.95'],
    ws_fanout_latency_ms: ['p(95)<150'], // target p95 < 150 ms
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_TARGET_URL || BASE_URL.replace('http', 'ws') + '/ws';

export default function (data) {
  const vuId = __VU;
  const iterId = __ITER;
  const email = `k6_user_${vuId}_${Date.now()}@snapland.test`;
  const password = 'Password123!';
  const displayName = `Tester ${vuId}`;

  // 1. Register user
  const regPayload = JSON.stringify({
    email: email,
    password: password,
    displayName: displayName,
  });

  const ip = `10.0.${Math.floor(vuId / 250)}.${(vuId % 250) + 1}`;
  const regHeaders = { 'Content-Type': 'application/json', 'X-Forwarded-For': ip };
  const regRes = http.post(`${BASE_URL}/api/v1/auth/register`, regPayload, { headers: regHeaders });
  
  let accessToken = '';

  if (regRes.status === 200 || regRes.status === 201) {
    // 2. Login to get token
    const loginPayload = JSON.stringify({ email: email, password: password });
    const loginRes = http.post(`${BASE_URL}/api/v1/auth/login`, loginPayload, { headers: regHeaders });
    if (loginRes.status === 200) {
      accessToken = loginRes.json('access_token');
    }
  }

  if (!accessToken) {
    connectionSuccess.add(0);
    return;
  }

  // 3. Obtain single-use WebSocket ticket
  const ticketRes = http.post(
    `${BASE_URL}/api/v1/auth/ws-ticket`,
    {},
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'X-Forwarded-For': ip,
      },
    }
  );

  if (ticketRes.status !== 200) {
    connectionSuccess.add(0);
    return;
  }

  const ticket = ticketRes.json('ticket');
  if (!ticket) {
    connectionSuccess.add(0);
    return;
  }

  // 4. Connect to WebSocket
  const url = `${WS_URL}?ticket=${ticket}`;
  const connectStart = Date.now();

  const response = ws.connect(url, {}, function (socket) {
    wsConnecting.add(Date.now() - connectStart);
    connectionSuccess.add(1);
    wsActiveConnections.add(1);

    let shapeId = `shape-${vuId}-${Date.now()}`;
    let isDrawing = false;
    let seq = 0;

    socket.on('open', () => {
      // Periodic cursor movement stream (10 Hz = every 100 ms)
      socket.setInterval(() => {
        const lat = 32.08 + (Math.random() - 0.5) * 0.04;
        const lng = 34.78 + (Math.random() - 0.5) * 0.04;
        const sentTime = Date.now();

        socket.send(
          JSON.stringify({
            type: 'CURSOR_MOVE',
            payload: { lat: lat, lng: lng, clientTime: sentTime },
          })
        );
        wsMessagesSent.add(1);
      }, 100);

      // Periodic collaborative drawing workflow
      socket.setInterval(() => {
        if (!isDrawing) {
          isDrawing = true;
          shapeId = `shape-${vuId}-${Date.now()}`;
          seq = 0;

          const startLat = 32.08 + (Math.random() - 0.5) * 0.02;
          const startLng = 34.78 + (Math.random() - 0.5) * 0.02;

          socket.send(
            JSON.stringify({
              type: 'DRAW_START',
              payload: {
                shapeId: shapeId,
                point: { lat: startLat, lng: startLng },
              },
            })
          );
          wsMessagesSent.add(1);
        } else if (seq < 5) {
          seq++;
          const curLat = 32.08 + (Math.random() - 0.5) * 0.02;
          const curLng = 34.78 + (Math.random() - 0.5) * 0.02;

          socket.send(
            JSON.stringify({
              type: 'DRAW_UPDATE',
              payload: {
                shapeId: shapeId,
                seq: seq,
                append: [{ lat: curLat, lng: curLng }],
              },
            })
          );
          wsMessagesSent.add(1);
        } else {
          isDrawing = false;
          // Commit polygon
          const polyPoints = [
            { lat: 32.08, lng: 34.78 },
            { lat: 32.085, lng: 34.78 },
            { lat: 32.085, lng: 34.785 },
            { lat: 32.08, lng: 34.785 },
            { lat: 32.08, lng: 34.78 },
          ];

          socket.send(
            JSON.stringify({
              type: 'DRAW_COMMIT',
              payload: {
                shapeId: shapeId,
                name: `Collab Polygon VU ${vuId}`,
                points: polyPoints,
              },
            })
          );
          wsMessagesSent.add(1);
        }
      }, 1000);
    });

    socket.on('message', (message) => {
      wsMessagesReceived.add(1);
      try {
        const parsed = JSON.parse(message);
        const batch = Array.isArray(parsed) ? parsed : [parsed];

        for (const item of batch) {
          if (item.type === 'PING') {
            socket.send(JSON.stringify({ type: 'PONG' }));
          } else if (item.type === 'ERROR' && item.payload && item.payload.code === 'RATE_LIMITED') {
            wsDroppedMessages.add(1);
          } else if (item.payload && item.payload.clientTime) {
            const fanoutMs = Date.now() - item.payload.clientTime;
            if (fanoutMs >= 0 && fanoutMs < 10000) {
              wsFanoutLatency.add(fanoutMs);
            }
          }
        }
      } catch (e) {
        // Ignored
      }
    });

    socket.on('close', () => {
      wsActiveConnections.add(-1);
    });

    socket.on('error', (e) => {
      wsActiveConnections.add(-1);
    });

    // Run connection for 20 seconds
    socket.setTimeout(() => {
      socket.close();
    }, 20000);
  });

  check(response, { 'WebSocket connected successfully': (r) => r && r.status === 101 });
}
