"""
SQL Isolation Anomalies - Init Script.
Creates tables and initial data.
Run after db is up, before screenshots.
"""

import asyncio
import os

from psycopg import AsyncConnection


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://isolation_user:isolation_pass@db:5432/isolation_db",
)


async def init():
    print(f"Connecting to: {DATABASE_URL}")
    conn = await AsyncConnection.connect(DATABASE_URL)
    
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
    print("Tables created.")
    
    async with conn.cursor() as cur:
        await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00), ('Konstantin', 500.00)")
    await conn.commit()
    print("Accounts: Oleg=1000, Konstantin=500")
    
    async with conn.cursor() as cur:
        await cur.execute("INSERT INTO products (name, price, quantity) VALUES ('Laptop', 50000.00, 10), ('Mouse', 1500.00, 100), ('Keyboard', 3000.00, 50)")
    await conn.commit()
    print("Products: Laptop, Mouse, Keyboard")
    
    await conn.close()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(init())