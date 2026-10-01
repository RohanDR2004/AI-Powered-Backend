def test_cors_header_present_for_allowed_origin(client):
    response = client.get("/", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_unknown_route_returns_404_without_leaking_internals(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert "traceback" not in response.text.lower()


def test_http_exception_headers_are_preserved(client):
    """Regression test: the custom HTTPException handler in main.py must
    forward exc.headers (e.g. WWW-Authenticate, Retry-After) rather than
    silently dropping them when building its JSONResponse."""
    response = client.get("/users/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
