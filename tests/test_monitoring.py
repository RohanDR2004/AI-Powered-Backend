def test_health_reports_database_status(client):
    response = client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "database" in body["checks"]
    assert "redis" in body["checks"]


def test_metrics_endpoint_exposed(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "python_gc_objects_collected_total" in response.text


def test_response_has_process_time_header(client):
    response = client.get("/")
    assert "x-process-time-ms" in response.headers
