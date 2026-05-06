"""
Wait for database to be ready.
"""

import asyncio
import os

import psycopg
from psycopg import AsyncConnection


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://isolation_user:isolation_pass@db:5432/isolation_db",
)


async def wait_for_db(retries: int = 20, delay: int = 2) -> bool:
    for attempt in range(1, retries + 1):
        try:
            conn = await AsyncConnection.connect(DATABASE_URL)
            await conn.close()
            return True
        except Exception:
            await asyncio.sleep(delay)
    return False


if __name__ == "__main__":
    if asyncio.run(wait_for_db()):
        print("Database is ready.")
    else:
        print("Could not connect to database.")
        exit(1)