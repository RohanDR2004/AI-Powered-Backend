def test_register_success(client):
    response = client.post(
        "/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_duplicate_email_fails(client, registered_user):
    response = client.post(
        "/auth/register",
        json={"name": "Dup", "email": registered_user["email"], "password": "password123"},
    )
    assert response.status_code == 400


def test_register_invalid_email_fails(client):
    response = client.post(
        "/auth/register",
        json={"name": "Bad", "email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == 422


def test_register_short_password_fails(client):
    response = client.post(
        "/auth/register",
        json={"name": "Bad", "email": "bad@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_success(client, registered_user):
    response = client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password_fails(client, registered_user):
    response = client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user_fails(client):
    response = client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "password123"},
    )
    assert response.status_code == 401
