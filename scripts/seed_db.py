import asyncio
import argparse
import random
import uuid
import asyncpg
from datetime import datetime, timezone

ISRAEL_BBOX = {
    "min_lng": 34.2,
    "max_lng": 35.8,
    "min_lat": 29.5,
    "max_lat": 33.3
}

async def seed_db(postgres_url: str, num_polygons: int):
    print(f"Connecting to {postgres_url}")
    conn = await asyncpg.connect(postgres_url)
    
    try:
        print(f"Seeding {num_polygons} polygons...")
        batch_size = 1000
        
        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users (id, email, password_hash, display_name, created_at, last_active, is_active) "
            "VALUES ($1, $2, 'hash', 'Seeder', $3, $3, true) ON CONFLICT DO NOTHING",
            user_id, f"seeder_{user_id}@example.com", datetime.now(timezone.utc)
        )
        
        for i in range(0, num_polygons, batch_size):
            batch = min(batch_size, num_polygons - i)
            records = []
            for _ in range(batch):
                area_id = uuid.uuid4()
                # Random center in Israel
                lng = random.uniform(ISRAEL_BBOX["min_lng"], ISRAEL_BBOX["max_lng"])
                lat = random.uniform(ISRAEL_BBOX["min_lat"], ISRAEL_BBOX["max_lat"])
                
                # Small square
                size = random.uniform(0.001, 0.01)
                geom_wkt = f"POLYGON(({lng} {lat}, {lng+size} {lat}, {lng+size} {lat+size}, {lng} {lat+size}, {lng} {lat}))"
                
                now = datetime.now(timezone.utc)
                records.append((
                    area_id,
                    f"Area {area_id}",
                    geom_wkt,
                    user_id,
                    user_id,
                    1,
                    now,
                    now
                ))
            
            await conn.executemany(
                """
                INSERT INTO areas (id, name, geom, created_by, last_edited_by, version, created_at, updated_at, area_km2)
                VALUES ($1, $2, ST_GeomFromText($3, 4326), $4, $5, $6, $7, $8, ST_Area(ST_GeomFromText($3, 4326)::geography)/1000000.0)
                """,
                records
            )
            print(f"Inserted {i + batch}/{num_polygons}")
            
    finally:
        await conn.close()
        print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Snapland DB")
    parser.add_argument("--polygons", type=int, default=10000)
    parser.add_argument("--url", type=str, default="postgresql://postgres:postgres@localhost:5432/snapland")
    args = parser.parse_args()
    
    asyncio.run(seed_db(args.url, args.polygons))
