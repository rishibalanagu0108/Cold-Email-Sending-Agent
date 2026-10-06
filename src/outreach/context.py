from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.models import (
    Company,
    Job,
    OutreachMessage,
    ProfileFact,
    ResumeVersion,
    Suppression,
)


def build_preparation_context(session: Session, limit: int = 20) -> dict:
    if not 1 <= limit <= 20:
        raise ValueError("Preparation limit must be between 1 and 20")
    resume = session.scalar(
        select(ResumeVersion)
        .where(ResumeVersion.confirmed.is_(True))
        .order_by(ResumeVersion.created_at.desc())
        .limit(1)
    )
    if not resume:
        raise ValueError("A confirmed resume version is required")

    facts = session.scalars(
        select(ProfileFact).where(
            ProfileFact.resume_version_id == resume.id,
            ProfileFact.confirmed.is_(True),
        )
    ).all()
    companies = session.scalars(select(Company).order_by(Company.canonical_domain)).all()
    jobs = session.scalars(select(Job)).all()
    outreach = session.scalars(select(OutreachMessage)).all()
    suppressions = session.scalars(select(Suppression)).all()

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "limit": limit,
        "resume": {
            "id": resume.id,
            "sha256": resume.sha256,
            "facts": [
                {
                    "category": fact.category,
                    "key": fact.key,
                    "value": fact.value,
                    "evidence_text": fact.evidence_text,
                    "page_number": fact.page_number,
                }
                for fact in facts
            ],
        },
        "known_companies": [
            {"id": company.id, "name": company.name, "domain": company.canonical_domain}
            for company in companies
        ],
        "known_jobs": [
            {
                "company_id": job.company_id,
                "fingerprint": job.fingerprint,
                "canonical_url": job.canonical_url,
            }
            for job in jobs
        ],
        "outreach": [
            {
                "company_id": message.company_id,
                "job_id": message.job_id,
                "status": message.status,
                "sent_at": message.sent_at.isoformat() if message.sent_at else None,
            }
            for message in outreach
        ],
        "suppressions": [
            {
                "company_id": item.company_id,
                "normalized_email": item.normalized_email,
                "reason": item.reason,
                "permanent": item.permanent,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            }
            for item in suppressions
        ],
    }
