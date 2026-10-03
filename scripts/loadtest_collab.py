#!/usr/bin/env python3
"""Collaborative WebSocket load test runner in Python.
Simulates 50, 100, and 200 concurrent users streaming cursors and drawing deltas,
measuring fanout latency, connection success, and dropped messages.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import secrets
import statistics
import time
import uuid
from typing import Any

import aiohttp
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bcrypt
from snapland.config import settings
from snapland.infrastructure.db.models import UserModel


async def ensure_loadtest_users(count: int = 200):
    """Pre-seeds loadtest users directly in Postgres for ultra-fast load testing."""
    import os
    db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://snapland:password@localhost:5432/snapland")
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    pwd_hash = bcrypt.hashpw(b"Password123!", bcrypt.gensalt(rounds=4)).decode()

    async with session_factory() as session:
        batch = []
        now = datetime.now(timezone.utc)
        for i in range(count):
            uid = uuid.uuid5(uuid.NAMESPACE_DNS, f"loadtest.vu.{i}.snapland.io")
            batch.append(
                {
                    "id": uid,
                    "email": f"loadtest_vu_{i}@snapland.test",
                    "password_hash": pwd_hash,
                    "display_name": f"VU-{i}",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        stmt = insert(UserModel).values(batch).on_conflict_do_nothing(index_elements=["email"])
        await session.execute(stmt)
        await session.commit()
    await engine.dispose()
    print(f"Ensured {count} pre-seeded virtual users in database.", flush=True)


async def obtain_ticket(session: aiohttp.ClientSession, base_url: str, user_idx: int) -> str | None:
    ip = f"10.0.{user_idx // 250}.{(user_idx % 250) + 1}"
    headers = {"X-Forwarded-For": ip}
    email = f"loadtest_vu_{user_idx}@snapland.test"
    password = "Password123!"

    try:
        async with session.post(
            f"{base_url}/api/v1/auth/login",
            headers=headers,
            json={"email": email, "password": password},
        ) as resp:
            if resp.status != 200:
                return None
            login_data = await resp.json()
            token = login_data["access_token"]

        ticket_headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": ip}
        async with session.post(f"{base_url}/api/v1/auth/ws-ticket", headers=ticket_headers) as resp:
            if resp.status != 200:
                return None
            ticket_data = await resp.json()
            return ticket_data["ticket"]
    except Exception:
        return None


async def simulate_user(ws_url: str, session: aiohttp.ClientSession, ticket: str, user_idx: int, duration_sec: float, stats: dict[str, Any]):
    ws_endpoint = f"{ws_url}?ticket={ticket}"
    try:
        t_start = time.monotonic()
        async with session.ws_connect(ws_endpoint, timeout=10.0) as ws:
            stats["conn_success"] += 1
            stats["connect_latencies"].append((time.monotonic() - t_start) * 1000.0)

            end_time = time.monotonic() + duration_sec
            last_cursor_time = time.monotonic()

            async def send_traffic():
                nonlocal last_cursor_time
                while time.monotonic() < end_time and not ws.closed:
                    now = time.monotonic()
                    if now - last_cursor_time >= 0.1:  # 10 Hz cursor
                        last_cursor_time = now
                        lat = 32.08 + (user_idx % 10) * 0.001
                        lng = 34.78 + (user_idx % 10) * 0.001
                        msg = {
                            "type": "CURSOR_MOVE",
                            "payload": {
                                "lat": lat,
                                "lng": lng,
                                "sent_at": time.time(),
                            },
                        }
                        await ws.send_str(json.dumps(msg))
                        stats["messages_sent"] += 1

                    await asyncio.sleep(0.05)

            async def receive_traffic():
                while time.monotonic() < end_time and not ws.closed:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            stats["messages_received"] += 1
                            try:
                                data = json.loads(msg.data)
                                items = data if isinstance(data, list) else [data]
                                for item in items:
                                    if item.get("type") == "ERROR" and item.get("payload", {}).get("code") == "RATE_LIMITED":
                                        stats["messages_dropped"] += 1
                                    elif item.get("payload", {}).get("sent_at"):
                                        latency_ms = (time.time() - item["payload"]["sent_at"]) * 1000.0
                                        if 0 <= latency_ms < 5000:
                                            stats["fanout_latencies"].append(latency_ms)
                            except Exception:
                                pass
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        continue

            await asyncio.gather(send_traffic(), receive_traffic(), return_exceptions=True)

    except Exception:
        stats["conn_failed"] += 1


async def run_scenario(base_url: str, ws_url: str, users_count: int, duration_sec: float = 6.0):
    stats = {
        "conn_success": 0,
        "conn_failed": 0,
        "connect_latencies": [],
        "fanout_latencies": [],
        "messages_sent": 0,
        "messages_received": 0,
        "messages_dropped": 0,
    }

    connector = aiohttp.TCPConnector(limit=users_count * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        print(f"\n--- Scenario: {users_count} Concurrent Users ---", flush=True)
        print(f"  Acquiring tickets for {users_count} virtual users...", flush=True)
        t0 = time.monotonic()
        ticket_tasks = [obtain_ticket(session, base_url, i) for i in range(users_count)]
        tickets = await asyncio.gather(*ticket_tasks)
        valid_tickets = [t for t in tickets if t is not None]
        ticket_time = time.monotonic() - t0

        print(f"  Tickets acquired: {len(valid_tickets)}/{users_count} in {ticket_time:.2f}s. Connecting WebSockets...", flush=True)
        t_ws = time.monotonic()
        ws_tasks = [
            simulate_user(ws_url, session, ticket, i, duration_sec, stats)
            for i, ticket in enumerate(valid_tickets)
        ]
        stats["conn_failed"] += users_count - len(valid_tickets)
        await asyncio.gather(*ws_tasks)
        stream_time = time.monotonic() - t_ws

    conn_total = stats["conn_success"] + stats["conn_failed"]
    conn_rate = (stats["conn_success"] / max(1, conn_total)) * 100.0

    fanout = sorted(stats["fanout_latencies"])
    p50_fanout = fanout[int(len(fanout) * 0.50)] if fanout else 0.0
    p95_fanout = fanout[int(len(fanout) * 0.95)] if fanout else 0.0
    p99_fanout = fanout[int(len(fanout) * 0.99)] if fanout else 0.0

    print(f"  Scenario Results ({users_count} Users):", flush=True)
    print(f"    Connection Success Rate: {conn_rate:.1f}% ({stats['conn_success']}/{conn_total})", flush=True)
    print(f"    Messages Sent: {stats['messages_sent']}, Received: {stats['messages_received']}, Dropped: {stats['messages_dropped']}", flush=True)
    print(f"    Fanout Latency (p50): {p50_fanout:.2f}ms", flush=True)
    print(f"    Fanout Latency (p95): {p95_fanout:.2f}ms", flush=True)
    print(f"    Fanout Latency (p99): {p99_fanout:.2f}ms", flush=True)

    return {
        "users": users_count,
        "conn_rate": conn_rate,
        "p50_fanout": p50_fanout,
        "p95_fanout": p95_fanout,
        "p99_fanout": p99_fanout,
        "sent": stats["messages_sent"],
        "received": stats["messages_received"],
        "dropped": stats["messages_dropped"],
    }


async def main():
    parser = argparse.ArgumentParser(description="Collaborative WebSocket load test runner")
    parser.add_argument("--port", type=int, default=8090, help="Port of target backend")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    ws_url = f"ws://127.0.0.1:{args.port}/ws"

    print("================ WEBSOCKET COLLABORATION LOAD TEST ================", flush=True)
    await ensure_loadtest_users(200)

    res_50 = await run_scenario(base_url, ws_url, 50, duration_sec=6.0)
    await asyncio.sleep(1.0)
    res_100 = await run_scenario(base_url, ws_url, 100, duration_sec=6.0)
    await asyncio.sleep(1.0)
    res_200 = await run_scenario(base_url, ws_url, 200, duration_sec=6.0)


if __name__ == "__main__":
    asyncio.run(main())
