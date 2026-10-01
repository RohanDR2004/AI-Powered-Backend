def test_create_task(client, auth_headers):
    response = client.post(
        "/tasks",
        json={"title": "Write report", "description": "Finish the report"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Write report"
    assert body["status"] == "pending"


def test_create_task_requires_auth(client):
    response = client.post("/tasks", json={"title": "No auth"})
    assert response.status_code in (401, 403)


def test_create_task_missing_title_fails(client, auth_headers):
    response = client.post("/tasks", json={"description": "No title"}, headers=auth_headers)
    assert response.status_code == 422


def test_list_tasks_only_returns_own_tasks(client, auth_headers):
    client.post("/tasks", json={"title": "Task 1"}, headers=auth_headers)
    client.post("/tasks", json={"title": "Task 2"}, headers=auth_headers)

    response = client.get("/tasks", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_tasks_pagination(client, auth_headers):
    for i in range(5):
        client.post("/tasks", json={"title": f"Task {i}"}, headers=auth_headers)

    response = client.get("/tasks?skip=0&limit=2", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client.get("/tasks?skip=4&limit=2", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_tasks_invalid_limit_fails(client, auth_headers):
    response = client.get("/tasks?limit=0", headers=auth_headers)
    assert response.status_code == 422
    response = client.get("/tasks?limit=500", headers=auth_headers)
    assert response.status_code == 422


def test_get_task_by_id(client, auth_headers):
    create_response = client.post("/tasks", json={"title": "Task"}, headers=auth_headers)
    task_id = create_response.json()["id"]

    response = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == task_id


def test_get_nonexistent_task_returns_404(client, auth_headers):
    response = client.get("/tasks/9999", headers=auth_headers)
    assert response.status_code == 404


def test_update_task(client, auth_headers):
    create_response = client.post("/tasks", json={"title": "Original"}, headers=auth_headers)
    task_id = create_response.json()["id"]

    response = client.put(
        f"/tasks/{task_id}",
        json={"title": "Updated", "status": "completed"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated"
    assert body["status"] == "completed"


def test_delete_task(client, auth_headers):
    create_response = client.post("/tasks", json={"title": "To delete"}, headers=auth_headers)
    task_id = create_response.json()["id"]

    delete_response = client.delete(f"/tasks/{task_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert get_response.status_code == 404


def test_user_cannot_access_other_users_task(client, auth_headers):
    create_response = client.post("/tasks", json={"title": "Private"}, headers=auth_headers)
    task_id = create_response.json()["id"]

    client.post(
        "/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    login_response = client.post(
        "/auth/login", json={"email": "other@example.com", "password": "password123"}
    )
    other_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.get(f"/tasks/{task_id}", headers=other_headers)
    assert response.status_code == 404
