"""
Quick test script to verify database connectivity.
"""

import asyncio
import os
import sys

import psycopg
from psycopg import AsyncConnection


DATABASE_URL = "postgresql://postgres:@localhost:5432/postgres"


async def test_db():
    try:
        conn = await AsyncConnection.connect(DATABASE_URL)
        print("Connected to postgres DB")
        
        # Check if isolation_db exists
        async with conn.execute("""
            SELECT 1 FROM pg_database WHERE datname = 'isolation_db'
        """) as cur:
            row = await cur.fetchone()
            if row is None:
                await conn.execute("CREATE DATABASE isolation_db")
                print("Created isolation_db")
            else:
                print("isolation_db already exists")
                
        await conn.close()
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_db())