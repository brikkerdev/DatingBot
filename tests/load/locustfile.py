"""
Load test for Dating Bot metrics endpoint and webhook.

Run:
  locust -f tests/load/locustfile.py --headless -u 50 -r 10 -t 60s --html tests/load/report.html
"""

import json
import random

from locust import HttpUser, between, task


class MetricsUser(HttpUser):
    """Hits the Prometheus metrics endpoint."""
    host = "http://localhost:9090"
    wait_time = between(0.5, 2)

    @task
    def get_metrics(self):
        self.client.get("/metrics")


class WebhookUser(HttpUser):
    """Simulates Telegram webhook updates (for webhook mode)."""
    host = "http://localhost:8443"
    wait_time = between(1, 3)

    @task(3)
    def send_start(self):
        uid = random.randint(100000, 999999)
        payload = {
            "update_id": random.randint(100000, 999999),
            "message": {
                "message_id": random.randint(1, 99999),
                "from": {"id": uid, "is_bot": False, "first_name": f"Load_{uid}"},
                "chat": {"id": uid, "type": "private"},
                "date": 1700000000,
                "text": "/start",
            },
        }
        self.client.post("/webhook", json=payload)

    @task(1)
    def send_text(self):
        uid = random.randint(100000, 999999)
        payload = {
            "update_id": random.randint(100000, 999999),
            "message": {
                "message_id": random.randint(1, 99999),
                "from": {"id": uid, "is_bot": False, "first_name": f"Load_{uid}"},
                "chat": {"id": uid, "type": "private"},
                "date": 1700000000,
                "text": "Смотреть анкеты",
            },
        }
        self.client.post("/webhook", json=payload)
