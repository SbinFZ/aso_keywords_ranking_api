from fastapi.testclient import TestClient
from app.main import app
import pytest
import app.main as main

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_popularity_mock(client, monkeypatch):
    async def fake_popularity(*args, **kwargs):
        return {
            "keyword": "tiktok",
            "country": "US",
            "priority": 123,
            "normalized_score": 88.8,
            "exact_match": True,
        }

    monkeypatch.setattr(main, "fetch_keyword_popularity", fake_popularity)
    response = client.get("/v1/keywords/popularity?keyword=tiktok&country=US")
    assert response.status_code == 200
    data = response.json()
    assert data["keyword"] == "tiktok"
    assert data["priority"] == 123

def test_hints_mock(client, monkeypatch):
    async def fake_hints(*args, **kwargs):
        return [{"term": "chat", "priority": 100, "normalized_score": 90}]

    monkeypatch.setattr(main, "fetch_hints", fake_hints)
    response = client.get("/v1/keywords/hints?keyword=chat&country=US")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1

def test_trends_mock(client, monkeypatch):
    async def fake_trends(*args, **kwargs):
        return [{"term": "foo", "priority": 1, "normalized_score": 10}]

    monkeypatch.setattr(main, "fetch_trends", fake_trends)
    response = client.get("/v1/keywords/trends?country=US")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1


def test_itunes_search_mock(client, monkeypatch):
    async def fake_search(*args, **kwargs):
        return {"result_count": 0, "results": []}

    monkeypatch.setattr(main, "itunes_search", fake_search)
    response = client.get("/v1/itunes/search?term=math&country=US")
    assert response.status_code == 200
    data = response.json()
    assert "result_count" in data


def test_itunes_lookup_requires_id_or_bundle(client):
    response = client.get("/v1/itunes/lookup?country=US")
    assert response.status_code == 400


def test_appstore_rss_invalid_limit(client):
    response = client.get("/v1/appstore/rss?country=us&limit=11")
    assert response.status_code == 400


def test_asa_request_requires_auth(client):
    response = client.post("/v1/asa/request", json={"path": "/api/v5/me"})
    assert response.status_code == 400
