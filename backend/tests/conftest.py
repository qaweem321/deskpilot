import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rag.store import HashEmbedder
from app.seed import DEMO_PASSWORD
from tests.fakes import ScriptedLLM

HEADERS = {"X-Requested-With": "deskpilot"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        jwt_secret="x" * 40,
        database_url=f"sqlite:///{tmp_path}/test.db",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        qdrant_url=":memory:",
        router_mode="keywords",
        kb_min_score=0.3,
    )


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def client(settings, llm) -> Iterator[TestClient]:
    app = create_app(settings, embedder=HashEmbedder(), llm=llm)
    with TestClient(app, headers=HEADERS) as c:
        yield c


def login(client: TestClient, who: str = "manager") -> TestClient:
    r = client.post("/api/auth/login", json={"email": f"{who}@deskpilot.test", "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return client


def events(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def of_type(evts: list[dict], kind: str) -> list[dict]:
    return [e for e in evts if e["type"] == kind]
