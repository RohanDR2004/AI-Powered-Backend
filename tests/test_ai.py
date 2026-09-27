def test_ai_generate_without_api_key_returns_503(client, auth_headers):
    response = client.post("/ai/generate", json={"prompt": "Explain ML simply"}, headers=auth_headers)
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_ai_generate_requires_auth(client):
    response = client.post("/ai/generate", json={"prompt": "Explain ML simply"})
    assert response.status_code in (401, 403)


def test_ai_generate_empty_prompt_fails(client, auth_headers):
    response = client.post("/ai/generate", json={"prompt": ""}, headers=auth_headers)
    assert response.status_code == 422
