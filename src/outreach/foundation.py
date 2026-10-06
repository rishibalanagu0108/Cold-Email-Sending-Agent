from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from outreach.identity import canonicalize_url, job_fingerprint, normalize_domain, normalize_text
from outreach.models import (
    Company,
    CompanyAlias,
    Job,
    JobSource,
    OutreachMessage,
    Reply,
    Suppression,
)


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: str | None = None


def get_or_create_company(session: Session, name: str, domain: str) -> Company:
    canonical_domain = normalize_domain(domain)
    company = session.scalar(select(Company).where(Company.canonical_domain == canonical_domain))
    if company:
        return company
    alias = session.scalar(
        select(CompanyAlias).where(CompanyAlias.alias_domain == canonical_domain)
    )
    if alias:
        return session.get_one(Company, alias.company_id)
    company = Company(name=name.strip(), canonical_domain=canonical_domain)
    session.add(company)
    session.flush()
    return company


def add_company_alias(session: Session, company: Company, domain: str) -> CompanyAlias:
    alias_domain = normalize_domain(domain)
    if alias_domain == company.canonical_domain:
        raise ValueError("Alias cannot equal the canonical domain")
    existing_company = session.scalar(
        select(Company).where(Company.canonical_domain == alias_domain)
    )
    if existing_company and existing_company.id != company.id:
        raise ValueError("Alias belongs to another canonical company")
    existing = session.scalar(select(CompanyAlias).where(CompanyAlias.alias_domain == alias_domain))
    if existing:
        if existing.company_id != company.id:
            raise ValueError("Alias belongs to another canonical company")
        return existing
    alias = CompanyAlias(company_id=company.id, alias_domain=alias_domain)
    session.add(alias)
    session.flush()
    return alias


def get_or_create_job(
    session: Session,
    *,
    company: Company,
    title: str,
    location: str,
    description: str,
    source_name: str,
    source_url: str,
    retrieved_at: datetime,
    source_job_id: str | None = None,
    posted_at: datetime | None = None,
) -> Job:
    canonical_url = canonicalize_url(source_url)
    if source_job_id:
        source = session.scalar(
            select(JobSource).where(
                JobSource.source_name == source_name.strip().lower(),
                JobSource.source_job_id == source_job_id.strip(),
            )
        )
        if source:
            return session.get_one(Job, source.job_id)

    fingerprint = job_fingerprint(title, location, description)
    job = session.scalar(
        select(Job).where(Job.company_id == company.id, Job.fingerprint == fingerprint)
    )
    if not job:
        job = Job(
            company_id=company.id,
            title=title.strip(),
            normalized_title=normalize_text(title),
            location=location.strip(),
            description=description.strip(),
            canonical_url=canonical_url,
            fingerprint=fingerprint,
            posted_at=posted_at,
        )
        session.add(job)
        session.flush()

    known_source = session.scalar(
        select(JobSource).where(JobSource.job_id == job.id, JobSource.source_url == canonical_url)
    )
    if not known_source:
        session.add(
            JobSource(
                job_id=job.id,
                source_name=source_name.strip().lower(),
                source_job_id=source_job_id.strip() if source_job_id else None,
                source_url=canonical_url,
                retrieved_at=_aware(retrieved_at),
            )
        )
        session.flush()
    return job


def company_eligibility(
    session: Session,
    company_id: str,
    candidate_job_fingerprint: str,
    *,
    at: datetime | None = None,
    cooldown_days: int = 90,
) -> Eligibility:
    now = _aware(at or datetime.now(UTC))
    suppression = session.scalar(
        select(Suppression).where(
            Suppression.company_id == company_id,
            or_(Suppression.permanent.is_(True), Suppression.expires_at > now),
        )
    )
    if suppression:
        return Eligibility(False, "company_suppressed")

    reply = session.scalar(
        select(Reply)
        .join(OutreachMessage, Reply.outreach_message_id == OutreachMessage.id)
        .where(OutreachMessage.company_id == company_id)
        .limit(1)
    )
    if reply:
        return Eligibility(False, "company_replied")

    latest = session.scalar(
        select(OutreachMessage)
        .where(
            OutreachMessage.company_id == company_id,
            OutreachMessage.status == "sent",
            OutreachMessage.sent_at.is_not(None),
        )
        .order_by(OutreachMessage.sent_at.desc())
        .limit(1)
    )
    if not latest:
        return Eligibility(True)
    sent_at = _aware(latest.sent_at)
    if now - sent_at < timedelta(days=cooldown_days):
        return Eligibility(False, "company_cooldown")
    previous_job = session.get(Job, latest.job_id)
    if previous_job and previous_job.fingerprint == candidate_job_fingerprint:
        return Eligibility(False, "same_role_after_cooldown")
    return Eligibility(True)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
