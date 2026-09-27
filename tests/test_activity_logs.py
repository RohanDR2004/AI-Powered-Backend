def test_login_creates_activity_log(client, auth_headers):
    response = client.get("/activity-logs", headers=auth_headers)
    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()]
    assert "login" in actions


def test_task_actions_create_activity_logs(client, auth_headers):
    create_response = client.post("/tasks", json={"title": "Logged task"}, headers=auth_headers)
    task_id = create_response.json()["id"]
    client.put(f"/tasks/{task_id}", json={"title": "Updated"}, headers=auth_headers)
    client.delete(f"/tasks/{task_id}", headers=auth_headers)

    response = client.get("/activity-logs", headers=auth_headers)
    actions = [entry["action"] for entry in response.json()]
    assert "task_created" in actions
    assert "task_updated" in actions
    assert "task_deleted" in actions


def test_activity_logs_require_auth(client):
    response = client.get("/activity-logs")
    assert response.status_code in (401, 403)


def test_activity_logs_are_user_scoped(client, auth_headers):
    client.post(
        "/auth/register",
        json={"name": "Other", "email": "other2@example.com", "password": "password123"},
    )
    login_response = client.post(
        "/auth/login", json={"email": "other2@example.com", "password": "password123"}
    )
    other_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.get("/activity-logs", headers=other_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["action"] == "login"
