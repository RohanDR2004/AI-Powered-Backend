"""Locust load test for the AI-Powered Backend Platform.

Run (against a locally running `uvicorn app.main:app`):
    locust -f locustfile.py --host http://127.0.0.1:8000

Headless example (10 users, spawn rate 2/s, 30s):
    locust -f locustfile.py --host http://127.0.0.1:8000 \
        --headless -u 10 -r 2 -t 30s --csv=locust_report

Each simulated user registers once (unique email), logs in, then repeatedly
lists and creates tasks and hits the health check — the endpoints a real
client would call most often. Never run this against a production
deployment or with real credentials/API keys.
"""

import uuid

from locust import HttpUser, between, task


class BackendUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.email = f"loadtest_{uuid.uuid4().hex[:10]}@example.com"
        self.password = "LoadTestPass123"
        self.client.post(
            "/auth/register",
            json={"name": "Load Test", "email": self.email, "password": self.password},
        )
        response = self.client.post(
            "/auth/login", json={"email": self.email, "password": self.password}
        )
        token = response.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {token}"}

    @task(5)
    def health_check(self):
        self.client.get("/")

    @task(3)
    def list_tasks(self):
        self.client.get("/tasks", headers=self.headers)

    @task(2)
    def create_task(self):
        self.client.post(
            "/tasks",
            json={"title": "Load test task", "description": "created by locust"},
            headers=self.headers,
        )

    @task(1)
    def login_again(self):
        self.client.post("/auth/login", json={"email": self.email, "password": self.password})
