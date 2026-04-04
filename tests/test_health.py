"""Integration tests for the health endpoint."""

from fastapi.testclient import TestClient

from fastapistock.main import app

client = TestClient(app)


def test_health_check() -> None:
    """GET /health returns the standard ResponseEnvelope with status ok."""
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'success'
    assert body['data'] == {'status': 'ok'}
    assert body['message'] == ''
