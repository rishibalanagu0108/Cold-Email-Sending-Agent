from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from outreach.bundles import PreparationBundle, import_bundle
from outreach.models import Company, DiscoveryRun, Job, JobMatch, MatchEvidence, ResumeVersion
from tests.factories import bundle_payload, candidate_payload, make_bundle


def _confirmed_resume(session: Session) -> ResumeVersion:
    resume = ResumeVersion(
        sha256="c" * 64,
        original_filename="resume.pdf",
        local_path="/private/resume.pdf",
        confirmed=True,
    )
    session.add(resume)
    session.commit()
    return resume


def test_bundle_rejects_more_than_twenty_eligible_companies() -> None:
    candidates = [
        candidate_payload(company=f"Company {index}", domain=f"company-{index}.ai")
        for index in range(21)
    ]
    with pytest.raises(ValidationError, match="at most 20"):
        PreparationBundle.model_validate(bundle_payload("resume-1", candidates))


def test_bundle_rejects_duplicate_company_domains() -> None:
    candidates = [
        candidate_payload(company="One", domain="example.ai"),
        candidate_payload(company="Two", domain="www.example.ai"),
    ]
    with pytest.raises(ValidationError, match="distinct companies"):
        PreparationBundle.model_validate(bundle_payload("resume-1", candidates))


def test_import_is_atomic_and_idempotent(session: Session) -> None:
    resume = _confirmed_resume(session)
    bundle = make_bundle(resume.id)

    first = import_bundle(session, bundle)
    second = import_bundle(session, bundle)

    assert first.imported == 1
    assert second.duplicate_run is True
    assert session.scalar(select(func.count()).select_from(DiscoveryRun)) == 1
    assert session.scalar(select(func.count()).select_from(Company)) == 1
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert session.scalar(select(func.count()).select_from(JobMatch)) == 1
    assert session.scalar(select(func.count()).select_from(MatchEvidence)) == 3


def test_rejected_candidate_is_stored_with_reason(session: Session) -> None:
    resume = _confirmed_resume(session)
    rejected = candidate_payload(status="rejected", rejection_reason="seniority_mismatch")
    rejected["source_job_id"] = "rejected-1"
    bundle = make_bundle(resume.id, [rejected])

    result = import_bundle(session, bundle)
    match = session.scalar(select(JobMatch))

    assert result.rejected == 1
    assert match is not None
    assert match.status == "rejected"
    assert match.rejection_reason == "seniority_mismatch"


def test_unknown_resume_rolls_back_everything(session: Session) -> None:
    bundle = make_bundle("missing-resume")
    with pytest.raises(ValueError, match="unknown or unconfirmed"):
        import_bundle(session, bundle)
    assert session.scalar(select(func.count()).select_from(DiscoveryRun)) == 0
    assert session.scalar(select(func.count()).select_from(Company)) == 0
