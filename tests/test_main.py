from fastapi.testclient import TestClient
from app.main import app
import pytest

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_popularity_integration(client):
    response = client.get("/v1/keywords/popularity?keyword=tiktok&country=US")
    if response.status_code != 200:
        print(f"DEBUG: Error response: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data["keyword"] == "tiktok"
    assert "priority" in data
    assert data["priority"] > 0
    assert "normalized_score" in data
    # We expect tiktok to be popular
    print(f"DEBUG: Data for tiktok: {data}")

def test_hints_integration(client):
    response = client.get("/v1/keywords/hints?keyword=chat&country=US")
    if response.status_code != 200:
        print(f"DEBUG: Error response: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) > 0
    print(f"DEBUG: Hints for chat: {data['items'][0]}")

# def test_trends_integration(client):
#     response = client.get("/v1/keywords/trends?country=US")
#     if response.status_code != 200:
#         print(f"DEBUG: Trends Error: {response.text}")
#     assert response.status_code == 200
#     data = response.json()
#     assert "items" in data
#     assert len(data["items"]) > 0
#     print(f"DEBUG: Trends top item: {data['items'][0]}")
