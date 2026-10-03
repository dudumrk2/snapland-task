import ws from 'k6/ws';
import http from 'k6/http';
import { check, sleep } from 'k6';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

export const options = {
    scenarios: {
        ws_collab: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '30s', target: 50 },
                { duration: '1m', target: 50 },
                { duration: '30s', target: 0 },
            ],
            gracefulRampDown: '10s',
        },
    },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8000';

export default function () {
    // 1. Register & Login to get token
    const email = `test_${randomString(8)}@example.com`;
    const pwd = 'password123';
    
    let res = http.post(`${BASE_URL}/api/v1/register`, JSON.stringify({
        email: email,
        password: pwd,
        display_name: `User_${randomString(4)}`
    }), { headers: { 'Content-Type': 'application/json' } });
    
    check(res, { 'registered': (r) => r.status === 200 || r.status === 201 });
    
    res = http.post(`${BASE_URL}/api/v1/login`, JSON.stringify({
        email: email,
        password: pwd
    }), { headers: { 'Content-Type': 'application/json' } });
    
    check(res, { 'logged in': (r) => r.status === 200 });
    const token = res.json('access_token');
    
    // 2. Get WS Ticket
    res = http.post(`${BASE_URL}/api/v1/ws-ticket`, null, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    check(res, { 'got ticket': (r) => r.status === 200 });
    const ticket = res.json('ticket');
    
    // 3. Connect to WS
    const url = `${WS_URL}/ws?ticket=${ticket}`;
    
    const response = ws.connect(url, null, function (socket) {
        socket.on('open', function () {
            console.log('connected');
            
            // Send cursor move
            socket.setInterval(function () {
                socket.send(JSON.stringify({
                    type: 'CURSOR_MOVE',
                    payload: {
                        lat: 31.0 + Math.random(),
                        lng: 34.0 + Math.random()
                    }
                }));
            }, 1000);
            
            // Send drawing updates
            socket.setInterval(function () {
                socket.send(JSON.stringify({
                    type: 'DRAW_UPDATE',
                    payload: {
                        shapeId: 'shape_' + randomString(6),
                        seq: 1,
                        fromIndex: 0,
                        append: [{ lat: 31.5, lng: 34.5 }]
                    }
                }));
            }, 5000);
        });

        socket.on('message', function (msg) {
            // just receive
        });

        socket.on('close', function () {
            console.log('disconnected');
        });
        
        socket.setTimeout(function () {
            socket.close();
        }, 60000); // stay connected for 60s
    });
    
    check(response, { 'ws status is 101': (r) => r && r.status === 101 });
}
