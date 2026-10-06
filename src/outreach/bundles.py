from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.contacts import ContactInput as ContactRecordInput
from outreach.contacts import store_verified_contact
from outreach.foundation import company_eligibility, get_or_create_company, get_or_create_job
from outreach.identity import job_fingerprint, normalize_domain
from outreach.matching import AI_ROLE_FAMILIES
from outreach.models import DiscoveryRun, JobMatch, MatchEvidence, ResumeVersion
from outreach.verification import VerificationEvidence


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreInput(StrictModel):
    role_alignment: int = Field(ge=0, le=35)
    demonstrated_skills: int = Field(ge=0, le=30)
    experience_seniority: int = Field(ge=0, le=20)
    location_eligibility: int = Field(ge=0, le=10)
    evidence_quality: int = Field(ge=0, le=5)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class EvidenceInput(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    evidence_type: Literal["resume", "job", "company"]
    claim: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    source_url: HttpUrl | None = None
    retrieved_at: datetime | None = None

    @model_validator(mode="after")
    def external_evidence_has_source(self) -> EvidenceInput:
        if self.evidence_type in {"job", "company"} and (
            self.source_url is None or self.retrieved_at is None
        ):
            raise ValueError("Job and company evidence require URL and retrieval time")
        return self


class VerificationInput(StrictModel):
    status: Literal["verified", "unverified", "unknown", "risky", "invalid", "catch_all"]
    method: Literal["official_public", "free_provider"]
    verified_at: datetime
    domain_accepts_mail: bool
    catch_all: bool = False
    evidence_url: HttpUrl | None = None
    evidence_excerpt: str | None = None
    provider: str | None = Field(default=None, max_length=100)
    provider_result: str | None = Field(default=None, max_length=100)


class ContactInput(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    email: EmailStr
    source_url: HttpUrl
    professional: bool
    public_professional: bool = False
    verification: VerificationInput


class CandidateInput(StrictModel):
    company_name: str = Field(min_length=1, max_length=255)
    company_domain: str = Field(min_length=3, max_length=255)
    company_stage: Literal["early", "medium", "large", "unknown"] = "unknown"
    title: str = Field(min_length=1, max_length=255)
    role_family: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=255)
    work_arrangement: Literal["remote", "hybrid", "onsite", "unknown"]
    description: str = Field(min_length=20)
    source_name: str = Field(min_length=1, max_length=100)
    source_job_id: str | None = Field(default=None, max_length=255)
    source_url: HttpUrl
    posted_at: datetime | None
    is_open: bool
    is_paid: bool
    location_eligible: bool
    seniority_eligible: bool
    status: Literal["eligible", "rejected"]
    rejection_reason: str | None = Field(default=None, max_length=100)
    score: ScoreInput
    evidence: list[EvidenceInput] = Field(min_length=1)
    contact: ContactInput | None = None

    @model_validator(mode="after")
    def eligibility_is_supported(self) -> CandidateInput:
        if self.status == "rejected":
            if not self.rejection_reason:
                raise ValueError("Rejected candidates require a rejection reason")
            return self

        problems: list[str] = []
        if self.role_family not in AI_ROLE_FAMILIES:
            problems.append("unsupported AI role family")
        if not self.is_open:
            problems.append("job is closed")
        if not self.is_paid:
            problems.append("job is unpaid")
        if not self.location_eligible:
            problems.append("location is ineligible")
        if not self.seniority_eligible:
            problems.append("seniority is ineligible")
        if self.posted_at is None:
            problems.append("posted date is missing")
        if self.score.total < 70:
            problems.append("fit score is below 70")
        if self.contact is None:
            problems.append("verified contact is required")
        evidence_types = {item.evidence_type for item in self.evidence}
        if "job" not in evidence_types or "company" not in evidence_types:
            problems.append("job and company evidence are required")
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            problems.append("evidence IDs must be unique")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class PreparationBundle(StrictModel):
    schema_version: Literal["1.0"]
    run_idempotency_key: str = Field(min_length=8, max_length=100)
    generated_at: datetime
    resume_version_id: str = Field(min_length=1, max_length=36)
    candidates: list[CandidateInput] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_batch(self) -> PreparationBundle:
        eligible = [candidate for candidate in self.candidates if candidate.status == "eligible"]
        if len(eligible) > 20:
            raise ValueError("A preparation run may contain at most 20 eligible companies")
        domains = [normalize_domain(candidate.company_domain) for candidate in eligible]
        if len(domains) != len(set(domains)):
            raise ValueError("Eligible candidates must contain distinct companies")
        generated = _aware(self.generated_at)
        for candidate in eligible:
            posted = _aware(candidate.posted_at)  # type: ignore[arg-type]
            if posted > generated + timedelta(days=1):
                raise ValueError(f"{candidate.company_name}: posted date is in the future")
            if generated - posted > timedelta(days=7):
                raise ValueError(f"{candidate.company_name}: job is older than seven days")
        return self


class ImportResult(StrictModel):
    run_id: str
    duplicate_run: bool = False
    imported: int = 0
    rejected: int = 0
    skipped: int = 0


def load_bundle(path: Path) -> PreparationBundle:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read preparation bundle: {exc}") from exc
    return PreparationBundle.model_validate(payload)


def import_bundle(session: Session, bundle: PreparationBundle) -> ImportResult:
    existing = session.scalar(
        select(DiscoveryRun).where(DiscoveryRun.idempotency_key == bundle.run_idempotency_key)
    )
    if existing:
        return ImportResult(run_id=existing.id, duplicate_run=True)

    resume = session.get(ResumeVersion, bundle.resume_version_id)
    if not resume or not resume.confirmed:
        raise ValueError("Bundle references an unknown or unconfirmed resume version")

    run = DiscoveryRun(
        idempotency_key=bundle.run_idempotency_key,
        status="importing",
        candidate_count=len(bundle.candidates),
    )
    session.add(run)
    session.flush()
    counts = {"imported": 0, "rejected": 0, "skipped": 0}

    try:
        for candidate in bundle.candidates:
            company = get_or_create_company(
                session, candidate.company_name, candidate.company_domain
            )
            company.stage = candidate.company_stage
            fingerprint = job_fingerprint(
                candidate.title, candidate.location, candidate.description
            )
            status = candidate.status
            reason = candidate.rejection_reason
            if status == "eligible":
                eligibility = company_eligibility(session, company.id, fingerprint)
                if not eligibility.eligible:
                    status = "skipped"
                    reason = eligibility.reason

            job = get_or_create_job(
                session,
                company=company,
                title=candidate.title,
                location=candidate.location,
                description=candidate.description,
                source_name=candidate.source_name,
                source_job_id=candidate.source_job_id,
                source_url=str(candidate.source_url),
                retrieved_at=bundle.generated_at,
                posted_at=candidate.posted_at,
            )
            match = JobMatch(
                discovery_run_id=run.id,
                resume_version_id=resume.id,
                company_id=company.id,
                job_id=job.id,
                fit_score=candidate.score.total,
                score_breakdown=candidate.score.model_dump(),
                status="researched" if status == "eligible" else status,
                rejection_reason=reason,
            )
            session.add(match)
            session.flush()
            if status == "eligible" and candidate.contact:
                verification = candidate.contact.verification
                store_verified_contact(
                    session,
                    company,
                    ContactRecordInput(
                        name=candidate.contact.name,
                        role=candidate.contact.role,
                        email=str(candidate.contact.email),
                        source_url=str(candidate.contact.source_url),
                        verification=VerificationEvidence(
                            email=str(candidate.contact.email),
                            company_domain=company.canonical_domain,
                            professional=candidate.contact.professional,
                            public_professional=candidate.contact.public_professional,
                            method=verification.method,
                            status=verification.status,
                            verified_at=verification.verified_at,
                            domain_accepts_mail=verification.domain_accepts_mail,
                            catch_all=verification.catch_all,
                            evidence_url=(
                                str(verification.evidence_url)
                                if verification.evidence_url
                                else None
                            ),
                            evidence_excerpt=verification.evidence_excerpt,
                            provider=verification.provider,
                            provider_result=verification.provider_result,
                        ),
                    ),
                )
            for evidence in candidate.evidence:
                session.add(
                    MatchEvidence(
                        job_match_id=match.id,
                        evidence_type=evidence.evidence_type,
                        claim=evidence.claim,
                        source_url=str(evidence.source_url) if evidence.source_url else None,
                        source_text=evidence.source_text,
                        retrieved_at=evidence.retrieved_at,
                    )
                )
            counts["imported" if status == "eligible" else status] += 1
        run.status = "completed"
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ImportResult(run_id=run.id, **counts)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
