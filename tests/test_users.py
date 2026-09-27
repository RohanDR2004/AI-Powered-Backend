def test_get_me_requires_auth(client):
    response = client.get("/users/me")
    assert response.status_code in (401, 403)


def test_get_me_with_valid_token(client, auth_headers, registered_user):
    response = client.get("/users/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == registered_user["email"]


def test_get_me_with_invalid_token(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert response.status_code == 401
