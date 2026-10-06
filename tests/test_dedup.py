from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from outreach.foundation import (
    add_company_alias,
    company_eligibility,
    get_or_create_company,
    get_or_create_job,
)
from outreach.identity import canonicalize_url, job_fingerprint, normalize_domain
from outreach.models import (
    Approval,
    Contact,
    DiscoveryRun,
    Draft,
    JobMatch,
    OutreachMessage,
    ResumeVersion,
    SendBatch,
    Suppression,
)


def test_domain_and_url_canonicalization() -> None:
    assert normalize_domain("https://WWW.Example.com/jobs") == "example.com"
    assert canonicalize_url("HTTPS://EXAMPLE.com/jobs/42/?utm_source=x&b=2&a=1#apply") == (
        "https://example.com/jobs/42?a=1&b=2"
    )


def test_company_alias_and_job_sources_deduplicate(session: Session) -> None:
    company = get_or_create_company(session, "Example AI", "https://www.example.ai")
    assert get_or_create_company(session, "Example", "example.ai").id == company.id
    add_company_alias(session, company, "example.com")
    assert get_or_create_company(session, "Old Example", "www.example.com").id == company.id

    now = datetime.now(UTC)
    first = get_or_create_job(
        session,
        company=company,
        title="Agentic AI Engineer",
        location="Remote",
        description="Build reliable AI agents.",
        source_name="company",
        source_job_id="job-42",
        source_url="https://example.ai/jobs/42?utm_source=board",
        retrieved_at=now,
    )
    second = get_or_create_job(
        session,
        company=company,
        title="Agentic AI Engineer",
        location="Remote",
        description="Build reliable AI agents.",
        source_name="company",
        source_job_id="job-42",
        source_url="https://example.ai/jobs/42",
        retrieved_at=now,
    )
    session.commit()

    assert first.id == second.id
    assert len(first.sources) == 1


def _sent_outreach(session: Session, *, sent_at: datetime) -> tuple[str, str]:
    company = get_or_create_company(session, "Acme AI", "acme.ai")
    job = get_or_create_job(
        session,
        company=company,
        title="AI Engineer",
        location="Remote",
        description="Build AI systems",
        source_name="company",
        source_job_id="a1",
        source_url="https://acme.ai/jobs/a1",
        retrieved_at=sent_at,
    )
    resume = ResumeVersion(
        sha256="a" * 64,
        original_filename="resume.pdf",
        local_path="/private/resume.pdf",
        confirmed=True,
    )
    run = DiscoveryRun(idempotency_key="run-1")
    session.add_all([resume, run])
    session.flush()
    match = JobMatch(
        discovery_run_id=run.id,
        resume_version_id=resume.id,
        company_id=company.id,
        job_id=job.id,
        fit_score=90,
    )
    contact = Contact(
        company_id=company.id,
        name="Hiring Lead",
        role="CTO",
        email="cto@acme.ai",
        normalized_email="cto@acme.ai",
        source_url="https://acme.ai/team",
        professional=True,
    )
    session.add_all([match, contact])
    session.flush()
    draft = Draft(
        job_match_id=match.id,
        contact_id=contact.id,
        resume_version_id=resume.id,
        subject="AI Engineer",
        body="Hello",
        revision_hash="b" * 64,
        status="approved",
    )
    session.add(draft)
    session.flush()
    approval = Approval(draft_id=draft.id, revision_hash=draft.revision_hash, approved_at=sent_at)
    batch = SendBatch(idempotency_key="batch-1", status="sent")
    session.add_all([approval, batch])
    session.flush()
    session.add(
        OutreachMessage(
            batch_id=batch.id,
            company_id=company.id,
            job_id=job.id,
            contact_id=contact.id,
            draft_id=draft.id,
            approval_id=approval.id,
            idempotency_key="message-1",
            status="sent",
            gmail_message_id="gmail-1",
            sent_at=sent_at,
        )
    )
    session.commit()
    return company.id, job.fingerprint


def test_company_cooldown_and_distinct_role_rule(session: Session) -> None:
    now = datetime.now(UTC)
    company_id, prior_fingerprint = _sent_outreach(session, sent_at=now - timedelta(days=30))

    assert company_eligibility(session, company_id, "different", at=now).reason == (
        "company_cooldown"
    )

    old_time = now - timedelta(days=91)
    message = session.query(OutreachMessage).one()
    message.sent_at = old_time
    session.commit()
    assert company_eligibility(session, company_id, prior_fingerprint, at=now).reason == (
        "same_role_after_cooldown"
    )
    assert company_eligibility(session, company_id, "new-role", at=now).eligible is True


def test_suppression_always_blocks_company(session: Session) -> None:
    company = get_or_create_company(session, "Blocked AI", "blocked.ai")
    session.add(Suppression(company_id=company.id, reason="opt_out", permanent=True))
    session.commit()

    result = company_eligibility(
        session,
        company.id,
        job_fingerprint("AI Engineer", "Remote", "Build AI"),
    )
    assert result == result.__class__(False, "company_suppressed")
