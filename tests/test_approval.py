from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.bundles import import_bundle
from outreach.drafts import approve_draft, edit_draft, set_draft_status
from outreach.models import Approval, ContactVerification, Draft, ResumeVersion
from tests.factories import candidate_payload, make_bundle


def _prepared_draft(session: Session, tmp_path: Path) -> Draft:
    resume_path = tmp_path / "resume.pdf"
    resume_path.write_bytes(b"%PDF fixture")
    resume = ResumeVersion(
        sha256="2" * 64,
        original_filename="resume.pdf",
        local_path=str(resume_path),
        confirmed=True,
    )
    session.add(resume)
    session.commit()
    import_bundle(session, make_bundle(resume.id))
    return session.scalar(select(Draft))  # type: ignore[return-value]


def test_approval_records_exact_revision(session: Session, tmp_path: Path) -> None:
    draft = _prepared_draft(session, tmp_path)
    approval = approve_draft(session, draft.id)

    assert draft.status == "approved"
    assert approval.revision_hash == draft.revision_hash
    assert session.scalar(select(Approval).where(Approval.draft_id == draft.id))


def test_edit_invalidates_existing_approval(session: Session, tmp_path: Path) -> None:
    draft = _prepared_draft(session, tmp_path)
    approval = approve_draft(session, draft.id)
    old_hash = approval.revision_hash

    body = candidate_payload()["draft"]["body"].replace("Hello Ada", "Hello team")
    edit_draft(session, draft.id, subject="Updated subject", body=body)

    assert draft.status == "pending_review"
    assert draft.revision_hash != old_hash


def test_stale_verification_blocks_approval(session: Session, tmp_path: Path) -> None:
    draft = _prepared_draft(session, tmp_path)
    verification = session.scalar(select(ContactVerification))
    assert verification is not None
    verification.verified_at = datetime.now(UTC) - timedelta(days=31)
    session.commit()

    with pytest.raises(ValueError, match="stale"):
        approve_draft(session, draft.id)


def test_missing_attachment_blocks_approval(session: Session, tmp_path: Path) -> None:
    draft = _prepared_draft(session, tmp_path)
    Path(session.get_one(ResumeVersion, draft.resume_version_id).local_path).unlink()

    with pytest.raises(ValueError, match="attachment"):
        approve_draft(session, draft.id)


def test_reject_and_defer_are_explicit_states(session: Session, tmp_path: Path) -> None:
    draft = _prepared_draft(session, tmp_path)
    set_draft_status(session, draft.id, "deferred")
    assert draft.status == "deferred"
    set_draft_status(session, draft.id, "rejected")
    assert draft.status == "rejected"
