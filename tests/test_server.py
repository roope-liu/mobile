from server.stream_server import app


def test_stream_health():
    client = app.test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
