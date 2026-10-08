import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.api.routes import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

@patch("httpx.AsyncClient")
def test_test_trident_endpoint(mock_client_class, client):
    mock_client_instance = mock_client_class.return_value.__aenter__.return_value
    class MockResponse:
        status_code = 200
        url = "https://trident.ac.in/placementnotice/"
        content = b"Mock content"
        headers = {"server": "nginx", "content-type": "text/html"}
        text = "Mock content"
        
    mock_client_instance.get.return_value = MockResponse()
    
    response = client.get("/api/test-trident")
    assert response.status_code == 200
    data = response.json()
    assert data["status_code"] == 200
    assert data["final_url"] == "https://trident.ac.in/placementnotice/"
    assert data["server_header"] == "nginx"
    assert "Mock content" in data["body_preview"]
