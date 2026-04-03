from fastapi.testclient import TestClient

from fastapistock.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Test health endpoint returns ok status."""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
