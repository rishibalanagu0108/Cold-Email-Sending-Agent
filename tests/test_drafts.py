from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from outreach.bundles import PreparationBundle, import_bundle
from outreach.models import Draft, DraftClaim, ResumeVersion
from tests.factories import bundle_payload, candidate_payload, make_bundle


def _resume(session: Session, path: Path) -> ResumeVersion:
    resume = ResumeVersion(
        sha256="1" * 64,
        original_filename="resume.pdf",
        local_path=str(path),
        confirmed=True,
    )
    session.add(resume)
    session.commit()
    return resume


def test_bundle_import_creates_pending_evidence_backed_draft(
    session: Session, tmp_path: Path
) -> None:
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF fixture")
    resume = _resume(session, resume_path)

    result = import_bundle(session, make_bundle(resume.id))
    draft = session.scalar(select(Draft))

    assert result.imported == 1
    assert draft is not None and draft.status == "pending_review"
    assert 120 <= len(draft.body.split()) <= 180
    assert session.scalar(select(func.count()).select_from(DraftClaim)) == 2


def test_draft_claims_must_reference_existing_evidence() -> None:
    candidate = candidate_payload()
    candidate["draft"]["claims"][0]["evidence_ids"] = ["missing"]
    with pytest.raises(ValidationError, match="missing evidence"):
        PreparationBundle.model_validate(bundle_payload("resume-1", [candidate]))


def test_draft_length_is_enforced() -> None:
    candidate = candidate_payload()
    candidate["draft"]["body"] = "Too short."
    with pytest.raises(ValidationError, match="120–180"):
        PreparationBundle.model_validate(bundle_payload("resume-1", [candidate]))
