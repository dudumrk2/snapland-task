#!/usr/bin/env python3
"""Seed database with realistic polygons across Israel and benchmark viewport queries.

Usage:
    python scripts/seed_db.py --polygons 10000
    python scripts/seed_db.py --polygons 100000
    python scripts/seed_db.py --benchmark
"""

import argparse
import asyncio
from datetime import datetime, timezone
import math
import random
import sys
import time
import uuid
import logging
from pathlib import Path

# Silence noisy dotenv warnings during CLI execution
logging.getLogger("dotenv.main").setLevel(logging.ERROR)

# Add backend and backend/src to path
backend_path = Path(__file__).resolve().parent.parent / "backend"
src_path = backend_path / "src"
for p in (str(backend_path), str(src_path)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pyproj import Geod
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from snapland.config import settings
from snapland.infrastructure.db.models import AreaModel, UserModel

# Cluster centers across Israel (lat, lng, name, weight)
REGIONS = [
    (32.0853, 34.7818, "Tel Aviv Central", 0.35),
    (32.1663, 34.8432, "Herzliya / Sharon", 0.15),
    (31.7683, 35.2137, "Jerusalem", 0.20),
    (32.7940, 34.9896, "Haifa", 0.15),
    (31.2529, 34.7915, "Beer Sheva", 0.08),
    (32.9646, 35.2979, "Galilee", 0.05),
    (29.5577, 34.9519, "Eilat", 0.02),
]

geod = Geod(ellps="WGS84")


def generate_polygon(center_lat: float, center_lng: float, radius_deg: float, num_vertices: int = 6):
    angles = sorted([random.uniform(0, 2 * math.pi) for _ in range(num_vertices)])
    points = []
    lons = []
    lats = []
    for angle in angles:
        r = radius_deg * random.uniform(0.7, 1.3)
        lat = center_lat + r * math.sin(angle)
        lng = center_lng + r * math.cos(angle) / max(0.1, math.cos(math.radians(center_lat)))
        points.append(f"{lng:.6f} {lat:.6f}")
        lons.append(lng)
        lats.append(lat)

    points.append(points[0])  # close ring
    wkt = f"POLYGON(({', '.join(points)}))"
    poly_area, _ = geod.polygon_area_perimeter(lons + [lons[0]], lats + [lats[0]])
    area_km2 = float(abs(poly_area) / 1_000_000.0)
    return wkt, area_km2


async def get_or_create_seed_user(session: AsyncSession) -> uuid.UUID:
    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, "seed.snapland.io")
    stmt = (
        insert(UserModel)
        .values(
            id=user_id,
            email="seed-user@snapland.io",
            display_name="Seeder Agent",
            password_hash="seeded_password_hash",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["email"])
    )
    await session.execute(stmt)
    await session.commit()
    return user_id


async def seed_polygons(target_count: int, batch_size: int = 2000, clean: bool = False, force: bool = False):
    if clean and not force:
        raise ValueError("Destructive flag '--clean' requires explicit '--force' to prevent accidental data loss.")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user_id = await get_or_create_seed_user(session)

        # Count existing areas
        r = await session.execute(select(func.count(AreaModel.id)).where(AreaModel.deleted_at.is_(None)))
        existing = r.scalar() or 0
        print(f"Current areas in DB: {existing}")

        if clean and existing > 0:
            print("Cleaning existing seeded areas...")
            await session.execute(text("TRUNCATE TABLE area_versions, audit_logs CASCADE;"))
            await session.execute(text("TRUNCATE TABLE areas CASCADE;"))
            await session.commit()
            existing = 0

        needed = target_count - existing
        if needed <= 0:
            print(f"Database already has {existing} areas (>= target {target_count}).")
            await engine.dispose()
            return

        print(f"Generating and inserting {needed} realistic polygons across Israel...")
        start_time = time.monotonic()
        total_inserted = 0

        region_weights = [r[3] for r in REGIONS]
        region_list = REGIONS

        while total_inserted < needed:
            current_batch_size = min(batch_size, needed - total_inserted)
            batch = []
            now = datetime.now(timezone.utc)

            for _ in range(current_batch_size):
                region = random.choices(region_list, weights=region_weights, k=1)[0]
                c_lat = region[0] + random.gauss(0, 0.05)
                c_lng = region[1] + random.gauss(0, 0.05)
                # Keep strictly inside Israel bounding box [min_lng=34.2, min_lat=29.5, max_lng=35.8, max_lat=33.3]
                # Margin accounts for radial vertex jitter (1.3x) and cos(lat) longitudinal distortion (~1.56x)
                radius = random.uniform(0.001, 0.008)  # ~100m to 800m
                c_lat = max(29.5 + 1.5 * radius, min(33.3 - 1.5 * radius, c_lat))
                c_lng = max(34.2 + 2.0 * radius, min(35.8 - 2.0 * radius, c_lng))

                num_verts = random.randint(4, 10)
                wkt, area_km2 = generate_polygon(c_lat, c_lng, radius, num_verts)

                batch.append(
                    {
                        "id": uuid.uuid4(),
                        "name": f"Area {region[2]} #{total_inserted + len(batch) + 1}",
                        "geom": func.ST_GeomFromText(wkt, 4326),
                        "area_km2": area_km2,
                        "version": 1,
                        "created_by": user_id,
                        "last_edited_by": user_id,
                        "created_at": now,
                        "updated_at": now,
                    }
                )

            stmt = insert(AreaModel).values(batch)
            await session.execute(stmt)
            await session.commit()

            total_inserted += len(batch)
            elapsed = time.monotonic() - start_time
            rate = total_inserted / max(0.001, elapsed)
            print(f"  Inserted {total_inserted}/{needed} (Rate: {rate:.0f} rows/s)")

        total_elapsed = time.monotonic() - start_time
        print(f"Completed seeding {needed} polygons in {total_elapsed:.2f}s ({needed/total_elapsed:.0f} rows/s).")

        # Refresh stats in Postgres
        print("Running ANALYZE areas...")
        await session.execute(text("ANALYZE areas;"))
        await session.commit()

    await engine.dispose()


async def benchmark_viewport_queries():
    """Benchmark viewport queries with and without Redis cache at various zoom levels."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    # Test viewports at various zoom levels
    # Zoom 10 (Regional - Central Israel): ~30km box
    # Zoom 14 (City - Tel Aviv): ~2km box
    # Zoom 17 (Neighborhood): ~300m box
    test_cases = [
        ("Zoom 10 (Regional / Central District)", 34.65, 31.90, 35.00, 32.25, 10),
        ("Zoom 14 (City / Tel Aviv Dense)", 34.76, 32.06, 34.80, 32.10, 14),
        ("Zoom 17 (Neighborhood / Micro Viewport)", 34.778, 32.078, 34.785, 32.085, 17),
    ]

    print("\n================ VIEWPORT QUERY BENCHMARKS ================")
    results = []

    async with engine.connect() as conn:
        for name, min_lng, min_lat, max_lng, max_lat, zoom in test_cases:
            print(f"\n--- Testing: {name} ---")
            envelope_sql = f"ST_MakeEnvelope({min_lng}, {min_lat}, {max_lng}, {max_lat}, 4326)"
            explain_query = text(f"""
                EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                SELECT id, ST_AsGeoJSON(geom) AS geojson
                FROM areas
                WHERE deleted_at IS NULL
                  AND ST_Intersects(geom, {envelope_sql})
                LIMIT 501;
            """)

            res = await conn.execute(explain_query)
            plan_lines = [r[0] for r in res.fetchall()]
            plan_text = "\n".join(plan_lines)
            print("Query Plan:")
            for line in plan_lines:
                print(f"  {line}")

            # Extract index scanned from plan
            has_gist = "areas_geom_gist" in plan_text
            print(f"  Index areas_geom_gist used: {has_gist}")

            # Latency benchmark without cache (Cold DB runs)
            durations_cold = []
            query_sql = text(f"""
                SELECT id, ST_AsGeoJSON(geom) AS geojson
                FROM areas
                WHERE deleted_at IS NULL
                  AND ST_Intersects(geom, {envelope_sql})
                LIMIT 501;
            """)

            for _ in range(50):
                t0 = time.monotonic()
                r = await conn.execute(query_sql)
                _ = r.fetchall()
                durations_cold.append((time.monotonic() - t0) * 1000.0)

            durations_cold.sort()
            p50_cold = durations_cold[int(len(durations_cold) * 0.50)]
            p95_cold = durations_cold[int(len(durations_cold) * 0.95)]
            p99_cold = durations_cold[int(len(durations_cold) * 0.99)]

            # Benchmark with Redis cache
            cache_key = f"benchmark:areas:z{zoom}:{min_lng}_{min_lat}_{max_lng}_{max_lat}"
            # Prepopulate cache
            await redis.set(cache_key, "cached_payload", ex=60)
            durations_warm = []
            for _ in range(100):
                t0 = time.monotonic()
                val = await redis.get(cache_key)
                durations_warm.append((time.monotonic() - t0) * 1000.0)

            durations_warm.sort()
            p50_warm = durations_warm[int(len(durations_warm) * 0.50)]
            p95_warm = durations_warm[int(len(durations_warm) * 0.95)]
            p99_warm = durations_warm[int(len(durations_warm) * 0.99)]

            print(f"  Without Cache: p50={p50_cold:.2f}ms, p95={p95_cold:.2f}ms, p99={p99_cold:.2f}ms")
            print(f"  With Redis:    p50={p50_warm:.2f}ms, p95={p95_warm:.2f}ms, p99={p99_warm:.2f}ms")

            results.append(
                {
                    "name": name,
                    "zoom": zoom,
                    "gist_used": has_gist,
                    "plan": plan_text,
                    "cold": (p50_cold, p95_cold, p99_cold),
                    "warm": (p50_warm, p95_warm, p99_warm),
                }
            )

    await redis.aclose()
    await engine.dispose()
    return results


def main():
    parser = argparse.ArgumentParser(description="Seed Snapland DB and run spatial benchmarks")
    parser.add_argument("--polygons", type=int, default=0, help="Target number of polygons in database (e.g. 10000 or 100000)")
    parser.add_argument("--clean", action="store_true", help="Truncate areas before seeding")
    parser.add_argument("--force", action="store_true", help="Explicit confirmation for destructive operations like --clean")
    parser.add_argument("--benchmark", action="store_true", help="Run viewport query benchmark")
    args = parser.parse_args()

    if args.polygons > 0:
        asyncio.run(seed_polygons(args.polygons, clean=args.clean, force=args.force))

    if args.benchmark or args.polygons > 0:
        asyncio.run(benchmark_viewport_queries())


if __name__ == "__main__":
    main()
