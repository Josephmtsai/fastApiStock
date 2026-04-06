"""Integration tests for the GET / API index endpoint."""

from fastapi.testclient import TestClient

from fastapistock.main import app

client = TestClient(app)

_KNOWN_PATHS = {'/health', '/api/v1/stock/{id}', '/api/v1/tgMessage/{id}', '/'}


class TestApiIndex:
    def test_returns_200(self) -> None:
        assert client.get('/').status_code == 200

    def test_envelope_structure(self) -> None:
        body = client.get('/').json()
        assert body['status'] == 'success'
        assert isinstance(body['data'], list)

    def test_each_entry_has_required_keys(self) -> None:
        data = client.get('/').json()['data']
        for entry in data:
            assert 'method' in entry
            assert 'path' in entry
            assert 'summary' in entry

    def test_known_routes_are_present(self) -> None:
        data = client.get('/').json()['data']
        paths = {entry['path'] for entry in data}
        assert _KNOWN_PATHS.issubset(paths)
