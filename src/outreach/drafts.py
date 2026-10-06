from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.foundation import company_eligibility
from outreach.models import (
    Approval,
    Contact,
    ContactVerification,
    Draft,
    DraftClaim,
    Job,
    JobMatch,
    MatchEvidence,
    ResumeVersion,
)


def draft_revision_hash(recipient: str, subject: str, body: str, resume_version_id: str) -> str:
    material = "\x1f".join(
        (recipient.strip().lower(), subject.strip(), body.strip(), resume_version_id)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_draft_text(subject: str, body: str) -> None:
    if not subject.strip() or len(subject) > 255:
        raise ValueError("Subject must contain 1–255 characters")
    word_count = len(body.split())
    if not 120 <= word_count <= 180:
        raise ValueError("Email body must contain 120–180 words")


def edit_draft(session: Session, draft_id: str, *, subject: str, body: str) -> Draft:
    draft = session.get(Draft, draft_id)
    if not draft:
        raise ValueError("Draft not found")
    validate_draft_text(subject, body)
    contact = session.get_one(Contact, draft.contact_id)
    draft.subject = subject.strip()
    draft.body = body.strip()
    draft.revision_hash = draft_revision_hash(
        contact.normalized_email, draft.subject, draft.body, draft.resume_version_id
    )
    draft.status = "pending_review"
    session.commit()
    return draft


def approve_draft(session: Session, draft_id: str, *, at: datetime | None = None) -> Approval:
    now = _aware(at or datetime.now(UTC))
    draft = session.get(Draft, draft_id)
    if not draft or draft.status != "pending_review":
        raise ValueError("Only a pending draft can be approved")
    validate_draft_text(draft.subject, draft.body)

    contact = session.get_one(Contact, draft.contact_id)
    if not contact.professional:
        raise ValueError("Contact is not professional")
    verification = session.scalar(
        select(ContactVerification)
        .where(ContactVerification.contact_id == contact.id)
        .order_by(ContactVerification.verified_at.desc())
        .limit(1)
    )
    if not verification or verification.status != "verified":
        raise ValueError("Contact is not verified")
    verified_at = _aware(verification.verified_at)
    if now - verified_at > timedelta(days=30):
        raise ValueError("Contact verification is stale")

    resume = session.get_one(ResumeVersion, draft.resume_version_id)
    if not resume.confirmed or not Path(resume.local_path).is_file():
        raise ValueError("Confirmed local resume attachment is required")
    if not session.scalar(select(DraftClaim).where(DraftClaim.draft_id == draft.id).limit(1)):
        raise ValueError("Draft has no evidence-backed claims")

    match = session.get_one(JobMatch, draft.job_match_id)
    evidence_types = set(
        session.scalars(
            select(MatchEvidence.evidence_type).where(MatchEvidence.job_match_id == match.id)
        ).all()
    )
    if not {"job", "company"} <= evidence_types:
        raise ValueError("Job and company evidence are required")
    job = session.get_one(Job, match.job_id)
    eligibility = company_eligibility(session, match.company_id, job.fingerprint, at=now)
    if not eligibility.eligible:
        raise ValueError(f"Company is not eligible: {eligibility.reason}")

    expected_hash = draft_revision_hash(
        contact.normalized_email, draft.subject, draft.body, draft.resume_version_id
    )
    draft.revision_hash = expected_hash
    approval = Approval(draft_id=draft.id, revision_hash=expected_hash, approved_at=now)
    draft.status = "approved"
    session.add(approval)
    session.commit()
    return approval


def set_draft_status(session: Session, draft_id: str, status: str) -> Draft:
    if status not in {"rejected", "deferred"}:
        raise ValueError("Draft status must be rejected or deferred")
    draft = session.get(Draft, draft_id)
    if not draft or draft.status not in {"pending_review", "deferred"}:
        raise ValueError("Draft cannot transition to the requested status")
    draft.status = status
    session.commit()
    return draft


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
