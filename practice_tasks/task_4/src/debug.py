"""
Quick debug test for SQL isolation.
"""

import asyncio
import os
import sys

from psycopg import AsyncConnection


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://isolation_user:isolation_pass@db:5432/isolation_db",
)


async def test():
    print(f"Connecting to: {DATABASE_URL}")
    try:
        conn = await AsyncConnection.connect(DATABASE_URL)
        print("Connected!")
        
        async with conn.execute("SELECT 1") as cur:
            row = await cur.fetchone()
            print(f"Result: {row}")
        
        await conn.close()
        print("Done!")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test())