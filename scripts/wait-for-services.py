"""Wait for PostgreSQL, Redis, RabbitMQ to be ready before starting the app."""

import socket
import sys
import time


def wait_for(host: str, port: int, name: str, timeout: int = 30) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.close()
            print(f"  {name} ({host}:{port}) is ready")
            return
        except OSError:
            time.sleep(1)
    print(f"  TIMEOUT waiting for {name} ({host}:{port})")
    sys.exit(1)


if __name__ == "__main__":
    print("Waiting for services...")
    wait_for("postgres", 5432, "PostgreSQL")
    wait_for("redis", 6379, "Redis")
    wait_for("rabbitmq", 5672, "RabbitMQ")
    wait_for("minio", 9000, "Minio")
    print("All services ready!")
