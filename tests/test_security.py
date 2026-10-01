def test_cors_header_present_for_allowed_origin(client):
    response = client.get("/", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_unknown_route_returns_404_without_leaking_internals(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert "traceback" not in response.text.lower()
