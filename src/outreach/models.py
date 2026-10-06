from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from outreach.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ResumeVersion(TimestampMixin, Base):
    __tablename__ = "resume_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    facts: Mapped[list[ProfileFact]] = relationship(
        back_populates="resume_version", cascade="all, delete-orphan"
    )


class ProfileFact(TimestampMixin, Base):
    __tablename__ = "profile_facts"
    __table_args__ = (
        UniqueConstraint("resume_version_id", "category", "key", "value", name="uq_profile_fact"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    resume_version: Mapped[ResumeVersion] = relationship(back_populates="facts")


class DiscoveryRun(TimestampMixin, Base):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="created", nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(30))

    aliases: Mapped[list[CompanyAlias]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="company", cascade="all, delete-orphan")


class CompanyAlias(TimestampMixin, Base):
    __tablename__ = "company_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias_domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    company: Mapped[Company] = relationship(back_populates="aliases")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "fingerprint", name="uq_job_company_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    company: Mapped[Company] = relationship(back_populates="jobs")
    sources: Mapped[list[JobSource]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobSource(TimestampMixin, Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("source_name", "source_job_id", name="uq_source_job_id"),
        UniqueConstraint("job_id", "source_url", name="uq_job_source_url"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    job: Mapped[Job] = relationship(back_populates="sources")


class JobMatch(TimestampMixin, Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("discovery_run_id", "company_id", name="uq_run_company_candidate"),
        CheckConstraint("fit_score >= 0 AND fit_score <= 100", name="ck_fit_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    discovery_run_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id"), nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="researched", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(100))


class MatchEvidence(TimestampMixin, Base):
    __tablename__ = "match_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_match_id: Mapped[str] = mapped_column(
        ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_key: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("normalized_email", name="uq_contact_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    professional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ContactVerification(TimestampMixin, Base):
    __tablename__ = "contact_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    evidence_url: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Draft(TimestampMixin, Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_match_id: Mapped[str] = mapped_column(ForeignKey("job_matches.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    resume_version_id: Mapped[str] = mapped_column(ForeignKey("resume_versions.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    revision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_review", nullable=False)


class DraftClaim(TimestampMixin, Base):
    __tablename__ = "draft_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("draft_id", "revision_hash", name="uq_draft_approval"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), nullable=False)
    revision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SendBatch(TimestampMixin, Base):
    __tablename__ = "send_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="created", nullable=False)


class OutreachMessage(TimestampMixin, Base):
    __tablename__ = "outreach_messages"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outreach_idempotency"),
        Index("ix_outreach_company_sent", "company_id", "sent_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("send_batches.id"), nullable=False)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), nullable=False)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))


class Reply(TimestampMixin, Base):
    __tablename__ = "replies"
    __table_args__ = (UniqueConstraint("gmail_message_id", name="uq_reply_gmail_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    outreach_message_id: Mapped[str] = mapped_column(
        ForeignKey("outreach_messages.id"), nullable=False, index=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(String(30), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Suppression(TimestampMixin, Base):
    __tablename__ = "suppressions"
    __table_args__ = (
        CheckConstraint(
            "company_id IS NOT NULL OR normalized_email IS NOT NULL",
            name="ck_suppression_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), index=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), index=True)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    permanent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
