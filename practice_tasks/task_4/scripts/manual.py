"""
Manual test runner for SQL isolation anomalies.
Run individual tests and capture screenshots at each step.

Usage:
    docker compose up -d db
    docker run --rm -it --network task_4_default isolation-test python scripts/manual.py
    
Then choose test number (1-4).
"""

import asyncio
import os
import sys
from pathlib import Path

from psycopg import AsyncConnection


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://isolation_user:isolation_pass@db:5432/isolation_db",
)


async def setup_tables(conn: AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute("""
            DROP TABLE IF EXISTS accounts CASCADE;
            DROP TABLE IF EXISTS products CASCADE;
            
            CREATE TABLE accounts (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                balance DECIMAL(10,2) NOT NULL DEFAULT 0
            );
            
            CREATE TABLE products (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                quantity INT NOT NULL DEFAULT 0
            );
        """)
    await conn.commit()


async def seed_dirty_read(conn: AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE TABLE accounts RESTART IDENTITY CASCADE")
        await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00), ('Konstantin', 500.00)")
    await conn.commit()
    print("[SETUP] dirty_read: Oleg=1000, Konstantin=500")


async def seed_non_repeatable(conn: AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE TABLE accounts RESTART IDENTITY CASCADE")
        await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00)")
    await conn.commit()
    print("[SETUP] non_repeatable_read: Oleg=1000")


async def seed_phantom(conn: AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE TABLE products RESTART IDENTITY CASCADE")
        await cur.execute("""
            INSERT INTO products (name, price, quantity) 
            VALUES ('Laptop', 50000.00, 10), ('Mouse', 1500.00, 100), ('Keyboard', 3000.00, 50)
        """)
    await conn.commit()
    print("[SETUP] phantom_read: 3 products")


async def seed_lost_update(conn: AsyncConnection) -> None:
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE TABLE accounts RESTART IDENTITY CASCADE")
        await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00)")
    await conn.commit()
    print("[SETUP] lost_update: Oleg=1000")


def print_test(name: str, steps: list):
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    print()


async def run_all_manual():
    conn = await AsyncConnection.connect(DATABASE_URL)
    await setup_tables(conn)
    await conn.close()
    
    print("\n" + "="*60)
    print("SQL ISOLATION ANOMALIES - MANUAL MODE")
    print("="*60)
    print("\nAvailable tests:")
    print("  1. Dirty Read")
    print("  2. Non-Repeatable Read")
    print("  3. Phantom Read")
    print("  4. Lost Update")
    print("\nEach test shows step-by-step what happens.")
    print("Take screenshots after each step as indicated.")
    
    tests = {
        "dirty_read": {
            "seed": seed_dirty_read,
            "steps": [
                "T1: BEGIN (isolation level READ UNCOMMITTED)",
                "T2: BEGIN; UPDATE accounts SET balance=2000 WHERE name='Oleg'",
                "T1: SELECT balance FROM accounts WHERE name='Oleg'  → ?",
                "T2: ROLLBACK",
                "T1: SELECT balance FROM accounts WHERE name='Oleg'  → ?"
            ]
        },
        "non_repeatable_read": {
            "seed": seed_non_repeatable,
            "steps": [
                "T1: BEGIN",
                "T1: SELECT balance FROM accounts WHERE name='Oleg'  → 1000",
                "T2: BEGIN; UPDATE accounts SET balance=1500; COMMIT",
                "T1: SELECT balance FROM accounts WHERE name='Oleg'  → ?"
            ]
        },
        "phantom_read": {
            "seed": seed_phantom,
            "steps": [
                "T1: BEGIN",
                "T1: SELECT COUNT(*) FROM products  → 3",
                "T2: BEGIN; INSERT INTO products VALUES ('Monitor',15000,25); COMMIT",
                "T1: SELECT COUNT(*) FROM products  → ?"
            ]
        },
        "lost_update": {
            "seed": seed_lost_update,
            "steps": [
                "T1: BEGIN; SELECT balance FROM accounts WHERE name='Oleg'  → 1000",
                "T2: BEGIN; SELECT balance FROM accounts WHERE name='Oleg'  → 1000",
                "T1: UPDATE accounts SET balance=1100; COMMIT",
                "T2: UPDATE accounts SET balance=1200; COMMIT",
                "SELECT balance FROM accounts WHERE name='Oleg'  → ?"
            ]
        }
    }
    
    for name, data in tests.items():
        print_test(name, data["steps"])
        print("To run this test:")
        print(f"  docker run --rm -it --network task_4_default isolation-test \\")
        print(f"    python scripts/manual.py --test {name}")
        print()


if __name__ == "__main__":
    asyncio.run(run_all_manual())