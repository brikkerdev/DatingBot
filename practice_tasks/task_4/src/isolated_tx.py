"""
SQL Isolation Anomalies Runner - MySQL version.
Demonstrates 4 transaction anomalies: dirty read, non-repeatable read, phantom read, lost update.
Uses READ UNCOMMITTED as specified.
"""

import asyncio
import os
import json
from pathlib import Path

import aiomysql


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+aiomysql://isolation_user:isolation_pass@db:3306/isolation_db",
)

RESULTS_DIR = Path("/app/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = RESULTS_DIR / "run.log"


def log(msg: str):
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


async def wait_for_db(retries: int = 20, delay: int = 2) -> None:
    for attempt in range(1, retries + 1):
        try:
            pool = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                          password="isolation_pass", db="isolation_db")
            pool.close()
            await pool.wait_closed()
            log("Database is ready.")
            return
        except Exception as e:
            log(f"Waiting for database... attempt {attempt}/{retries}: {e}")
            await asyncio.sleep(delay)
    raise RuntimeError("Could not connect to database")


async def setup_tables(pool) -> None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DROP TABLE IF EXISTS accounts")
            await cur.execute("DROP TABLE IF EXISTS products")
            await cur.execute("""
                CREATE TABLE accounts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    balance DECIMAL(10,2) NOT NULL DEFAULT 0
                )
            """)
            await cur.execute("""
                CREATE TABLE products (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    price DECIMAL(10,2) NOT NULL,
                    quantity INT NOT NULL DEFAULT 0
                )
            """)


async def reset_and_seed(pool, anomaly: str) -> None:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE accounts")
            await cur.execute("TRUNCATE TABLE products")
            
            if anomaly == "dirty_read":
                await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00), ('Konstantin', 500.00)")
            elif anomaly == "non_repeatable_read":
                await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00)")
            elif anomaly == "phantom_read":
                await cur.execute("""
                    INSERT INTO products (name, price, quantity) 
                    VALUES ('Laptop', 50000.00, 10), ('Mouse', 1500.00, 100), ('Keyboard', 3000.00, 50)
                """)
            elif anomaly == "lost_update":
                await cur.execute("INSERT INTO accounts (name, balance) VALUES ('Oleg', 1000.00)")
        await conn.commit()


async def run_dirty_read(results: dict) -> None:
    log("[Dirty Read] Starting test with READ UNCOMMITTED...")
    log("[Dirty Read] Initial: Oleg=1000, Konstantin=500")
    
    pool = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                  password="isolation_pass", db="isolation_db", autocommit=False)
    
    await reset_and_seed(pool, "dirty_read")
    
    start_signal = asyncio.Event()
    ready_signal = asyncio.Event()
    
    async def tx1(conn):
        async with conn.cursor() as cur:
            await cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            await cur.execute("START TRANSACTION")
        
        ready_signal.set()
        await start_signal.wait()
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            balance = row[0]
            log(f"[TX1] READ (dirty): Oleg's balance = {balance}")
            results["tx1_first_read"] = str(balance)
        
        await asyncio.sleep(0.5)
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            balance = row[0]
            log(f"[TX1] READ after rollback: Oleg's balance = {balance}")
            results["tx1_second_read"] = str(balance)
    
    async def tx2(conn):
        await ready_signal.wait()
        
        async with conn.cursor() as cur:
            await cur.execute("START TRANSACTION")
            await cur.execute("UPDATE accounts SET balance = 2000.00 WHERE name = 'Oleg'")
            log("[TX2] UPDATE: Oleg's balance = 2000 (NOT COMMITTED)")
        
        await asyncio.sleep(0.2)
        
        start_signal.set()
        await asyncio.sleep(0.1)
        
        async with conn.cursor() as cur:
            await cur.execute("ROLLBACK")
        
        log("[TX2] ROLLBACK - changes reverted")
    
    async with pool.acquire() as conn1, pool.acquire() as conn2:
        await asyncio.gather(tx1(conn1), tx2(conn2))
    
    pool.close()
    await pool.wait_closed()
    
    if results.get("tx1_first_read") == "2000.00":
        results["outcome"] = "DIRTY_READ occurred - TX1 read uncommitted data"
        log("[Dirty Read] RESULT: Dirty read detected!")
    else:
        results["outcome"] = "DIRTY_READ not detected"
        log("[Dirty Read] RESULT: Not detected (MySQL prevents in this scenario)")


async def run_non_repeatable_read(results: dict) -> None:
    log("[Non-Repeatable Read] Starting test with READ COMMITTED (weaker level)...")
    log("[Non-Repeatable Read] Initial: Oleg=1000")
    
    pool = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                  password="isolation_pass", db="isolation_db", autocommit=False)
    
    await reset_and_seed(pool, "non_repeatable_read")
    
    start_signal = asyncio.Event()
    ready_signal = asyncio.Event()
    
    async def tx1(conn):
        async with conn.cursor() as cur:
            await cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            await cur.execute("START TRANSACTION")
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            balance = row[0]
            log(f"[TX1] First READ: Oleg's balance = {balance}")
            results["tx1_first_read"] = str(balance)
        
        ready_signal.set()
        await start_signal.wait()
        
        await asyncio.sleep(0.3)
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            balance = row[0]
            log(f"[TX1] Second READ: Oleg's balance = {balance}")
            results["tx1_second_read"] = str(balance)
        
        await conn.commit()
    
    async def tx2(conn):
        await ready_signal.wait()
        
        async with conn.cursor() as cur:
            await cur.execute("START TRANSACTION")
            await cur.execute("UPDATE accounts SET balance = 1500.00 WHERE name = 'Oleg'")
            log("[TX2] UPDATE: Oleg's balance = 1500")
            await cur.execute("COMMIT")
        
        log("[TX2] COMMIT")
        start_signal.set()
    
    async with pool.acquire() as conn1, pool.acquire() as conn2:
        await asyncio.gather(tx1(conn1), tx2(conn2))
    
    pool.close()
    await pool.wait_closed()
    
    if results.get("tx1_first_read") != results.get("tx1_second_read"):
        results["outcome"] = "NON_REPEATABLE_READ occurred"
        log("[Non-Repeatable Read] RESULT: Detected!")
    else:
        results["outcome"] = "NON_REPEATABLE_READ not detected"
        log("[Non-Repeatable Read] RESULT: Not detected")


async def run_phantom_read(results: dict) -> None:
    log("[Phantom Read] Starting test with READ COMMITTED...")
    
    pool = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                  password="isolation_pass", db="isolation_db", autocommit=False)
    
    await reset_and_seed(pool, "phantom_read")
    
    start_signal = asyncio.Event()
    ready_signal = asyncio.Event()
    
    async def tx1(conn):
        async with conn.cursor() as cur:
            await cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            await cur.execute("START TRANSACTION")
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM products")
            row = await cur.fetchone()
            count = row[0]
            log(f"[TX1] First READ: {count} products")
            results["tx1_first_count"] = str(count)
        
        ready_signal.set()
        await start_signal.wait()
        await asyncio.sleep(0.3)
        
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM products")
            row = await cur.fetchone()
            count = row[0]
            log(f"[TX1] Second READ: {count} products")
            results["tx1_second_count"] = str(count)
        
        await conn.commit()
    
    async def tx2(conn):
        await ready_signal.wait()
        
        async with conn.cursor() as cur:
            await cur.execute("START TRANSACTION")
            await cur.execute("INSERT INTO products (name, price, quantity) VALUES ('Monitor', 15000.00, 25)")
            log("[TX2] INSERT: Monitor added")
            await cur.execute("COMMIT")
        
        log("[TX2] COMMIT")
        start_signal.set()
    
    async with pool.acquire() as conn1, pool.acquire() as conn2:
        await asyncio.gather(tx1(conn1), tx2(conn2))
    
    pool.close()
    await pool.wait_closed()
    
    if results.get("tx1_first_count") != results.get("tx1_second_count"):
        results["outcome"] = "PHANTOM_READ occurred"
        log("[Phantom Read] RESULT: Detected!")
    else:
        results["outcome"] = "PHANTOM_READ not detected"
        log("[Phantom Read] RESULT: Not detected")


async def run_lost_update(results: dict) -> None:
    log("[Lost Update] Starting test...")
    log("[Lost Update] Initial: Oleg=1000")
    
    pool = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                  password="isolation_pass", db="isolation_db", autocommit=False)
    
    await reset_and_seed(pool, "lost_update")
    
    start_signal = asyncio.Event()
    ready_signal = asyncio.Event()
    
    async def tx1(conn):
        async with conn.cursor() as cur:
            await cur.execute("START TRANSACTION")
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            initial = float(row[0])
            log(f"[TX1] READ: Oleg's balance = {initial}")
            results["tx1_initial"] = str(initial)
        
        ready_signal.set()
        await start_signal.wait()
        
        new_balance = initial + 100
        async with conn.cursor() as cur:
            await cur.execute(f"UPDATE accounts SET balance = {new_balance} WHERE name = 'Oleg'")
            log(f"[TX1] UPDATE: SET balance = {new_balance} (was {initial} + 100)")
            await cur.execute("COMMIT")
        
        log("[TX1] COMMIT")
        results["tx1_final"] = str(new_balance)
    
    async def tx2(conn):
        await ready_signal.wait()
        
        async with conn.cursor() as cur:
            await cur.execute("START TRANSACTION")
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            initial = float(row[0])
            log(f"[TX2] READ: Oleg's balance = {initial}")
            results["tx2_initial"] = str(initial)
        
        new_balance = initial + 200
        async with conn.cursor() as cur:
            await cur.execute(f"UPDATE accounts SET balance = {new_balance} WHERE name = 'Oleg'")
            log(f"[TX2] UPDATE: SET balance = {new_balance} (was {initial} + 200)")
            await cur.execute("COMMIT")
        
        log("[TX2] COMMIT")
        results["tx2_final"] = str(new_balance)
        
        start_signal.set()
    
    async with pool.acquire() as conn1, pool.acquire() as conn2:
        await asyncio.gather(tx1(conn1), tx2(conn2))
    
    pool.close()
    await pool.wait_closed()
    
    pool2 = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                    password="isolation_pass", db="isolation_db")
    async with pool2.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT balance FROM accounts WHERE name = 'Oleg'")
            row = await cur.fetchone()
            final = row[0]
            log(f"[Final] Oleg's balance = {final}")
            results["final_balance"] = str(final)
    
    pool2.close()
    await pool2.wait_closed()
    
    if float(final) == 1100:
        results["outcome"] = "LOST_UPDATE occurred - update from TX1 was lost"
        log("[Lost Update] RESULT: Lost update detected! Expected 1200, got 1100")
    elif float(final) == 1200:
        results["outcome"] = "Update order: TX2 committed last"
        log("[Lost Update] RESULT: TX2 committed last, final = 1200")
    else:
        results["outcome"] = f"Final balance: {final}"
        log(f"[Lost Update] RESULT: Final = {final}")


async def run_all_anomalies() -> None:
    log("\n" + "=" * 60)
    log("SQL ISOLATION ANOMALIES - MYSQL")
    log("Demonstrating 4 transaction anomalies")
    log("=" * 60 + "\n")
    
    await wait_for_db()
    
    pool = await aiomysql.create_pool(host="db", port=3306, user="isolation_user", 
                                  password="isolation_pass", db="isolation_db")
    await setup_tables(pool)
    pool.close()
    await pool.wait_closed()
    
    anomalies = [
        ("dirty_read", run_dirty_read),
        ("non_repeatable_read", run_non_repeatable_read),
        ("phantom_read", run_phantom_read),
        ("lost_update", run_lost_update),
    ]
    
    for anomaly_name, run_func in anomalies:
        log(f"\n{'=' * 60}")
        log(f"Running: {anomaly_name.upper()}")
        log(f"{'=' * 60}")
        
        results = {"anomaly": anomaly_name}
        
        await run_func(results)
        
        result_file = RESULTS_DIR / f"{anomaly_name}.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        log(f"Results saved to: {result_file}")
        
        await asyncio.sleep(0.5)
    
    log("\n" + "=" * 60)
    log("All tests complete!")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_anomalies())