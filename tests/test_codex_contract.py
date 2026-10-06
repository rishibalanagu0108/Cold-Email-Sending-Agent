from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from outreach.bundles import PreparationBundle, load_bundle
from outreach.context import build_preparation_context
from outreach.models import ProfileFact, ResumeVersion
from tests.factories import bundle_payload


def test_bundle_round_trip_uses_strict_versioned_schema(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    payload = bundle_payload("resume-1")
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_bundle(path)

    assert loaded.schema_version == "1.0"
    assert loaded.model_dump(mode="json")["candidates"][0]["company_domain"] == "example.ai"
    assert PreparationBundle.model_json_schema()["additionalProperties"] is False


def test_context_contains_prior_state_but_no_secrets(session: Session) -> None:
    resume = ResumeVersion(
        sha256="d" * 64,
        original_filename="resume.pdf",
        local_path="/private/resume.pdf",
        confirmed=True,
    )
    resume.facts.append(
        ProfileFact(
            category="skill",
            key="python",
            value="Python",
            evidence_text="Built production systems with Python",
            page_number=1,
            confirmed=True,
        )
    )
    session.add(resume)
    session.commit()

    context = build_preparation_context(session, 20)
    serialized = json.dumps(context)

    assert context["limit"] == 20
    assert context["resume"]["id"] == resume.id
    assert context["resume"]["facts"][0]["value"] == "Python"
    assert "password" not in serialized.lower()
    assert "database_url" not in serialized.lower()
    assert "local_path" not in serialized.lower()


def test_runbook_preserves_manual_approval_boundary() -> None:
    runbook = Path("CODEX_RUNBOOK.md").read_text(encoding="utf-8")
    assert "sends nothing" in runbook
    assert "Do not approve or send anything" in runbook
    assert "at most 20 companies" in runbook
