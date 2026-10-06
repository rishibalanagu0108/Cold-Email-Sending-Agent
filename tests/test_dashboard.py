from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from outreach.bundles import import_bundle
from outreach.config import Settings
from outreach.db import Base
from outreach.models import Draft, ResumeVersion
from outreach.web import create_app
from tests.factories import make_bundle


def _client_with_draft(tmp_path: Path) -> tuple[TestClient, object, str]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF fixture")
    with Session(engine) as session:
        resume = ResumeVersion(
            sha256="3" * 64,
            original_filename="resume.pdf",
            local_path=str(resume_path),
            confirmed=True,
        )
        session.add(resume)
        session.commit()
        import_bundle(session, make_bundle(resume.id))
        draft_id = session.scalar(select(Draft.id))
    app = create_app(
        engine,
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            local_data_dir=tmp_path / "local",
        ),
    )
    return TestClient(app), engine, str(draft_id)


def test_dashboard_lists_and_opens_review_item(tmp_path: Path) -> None:
    client, _, draft_id = _client_with_draft(tmp_path)

    queue = client.get("/review")
    detail = client.get(f"/review/{draft_id}")

    assert queue.status_code == 200
    assert "Example AI" in queue.text
    assert detail.status_code == 200
    assert "Evidence" in detail.text
    assert "ada@example.ai" in detail.text


def test_dashboard_approval_and_edit_invalidation(tmp_path: Path) -> None:
    client, engine, draft_id = _client_with_draft(tmp_path)
    headers = {"Origin": "http://testserver"}

    approved = client.post(f"/drafts/{draft_id}/approve", headers=headers)
    body = make_bundle("unused").candidates[0].draft.body.replace("Hello Ada", "Hello team")
    edited = client.post(
        f"/drafts/{draft_id}/edit",
        data={"subject": "Updated subject", "body": body},
        headers=headers,
    )

    assert approved.status_code == 200
    assert edited.status_code == 200
    with Session(engine) as session:
        assert session.get_one(Draft, draft_id).status == "pending_review"


def test_dashboard_rejects_cross_origin_post(tmp_path: Path) -> None:
    client, _, draft_id = _client_with_draft(tmp_path)
    response = client.post(
        f"/drafts/{draft_id}/approve", headers={"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403


def test_dashboard_status_keeps_credentials_server_side(tmp_path: Path) -> None:
    client, _, _ = _client_with_draft(tmp_path)
    response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["host"] == "127.0.0.1"
    assert "password" not in response.text.lower()
