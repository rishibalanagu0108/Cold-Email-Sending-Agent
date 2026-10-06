from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.models import AuditEvent, ProfileFact, ResumeVersion


@dataclass(frozen=True)
class FactInput:
    category: str
    key: str
    value: str
    evidence_text: str
    page_number: int | None = None


def import_resume(session: Session, source: Path, data_dir: Path) -> ResumeVersion:
    source = source.expanduser().resolve()
    if source.suffix.lower() != ".pdf" or not source.is_file():
        raise ValueError("Resume must be an existing PDF file")
    content = source.read_bytes()
    if not content.startswith(b"%PDF"):
        raise ValueError("Resume does not contain a valid PDF header")

    digest = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(ResumeVersion).where(ResumeVersion.sha256 == digest))
    if existing:
        return existing

    resume_dir = data_dir.expanduser().resolve() / "resumes"
    resume_dir.mkdir(parents=True, exist_ok=True)
    destination = resume_dir / f"{digest}.pdf"
    if not destination.exists():
        shutil.copyfile(source, destination)

    try:
        reader = PdfReader(destination)
        extracted = "\n\n".join(
            (page.extract_text() or "").strip() for page in reader.pages
        ).strip()
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise ValueError("Resume PDF could not be parsed") from exc

    version = ResumeVersion(
        sha256=digest,
        original_filename=source.name,
        local_path=str(destination),
        extracted_text=extracted,
    )
    session.add(version)
    session.flush()
    session.add(
        AuditEvent(
            event_type="resume.imported",
            entity_type="resume_version",
            entity_id=version.id,
            details={"sha256": digest, "original_filename": source.name},
        )
    )
    return version


def replace_profile_facts(
    session: Session, resume: ResumeVersion, facts: list[FactInput]
) -> ResumeVersion:
    if not facts:
        raise ValueError("At least one evidenced profile fact is required")
    for fact in facts:
        if not all(
            (
                fact.category.strip(),
                fact.key.strip(),
                fact.value.strip(),
                fact.evidence_text.strip(),
            )
        ):
            raise ValueError("Each profile fact requires category, key, value, and evidence text")
        if fact.page_number is not None and fact.page_number < 1:
            raise ValueError("Page numbers are one-based")

    resume.facts.clear()
    resume.confirmed = False
    for fact in facts:
        resume.facts.append(
            ProfileFact(
                category=fact.category.strip(),
                key=fact.key.strip(),
                value=fact.value.strip(),
                evidence_text=fact.evidence_text.strip(),
                page_number=fact.page_number,
            )
        )
    session.flush()
    return resume


def confirm_profile(session: Session, resume: ResumeVersion) -> None:
    if not resume.facts:
        raise ValueError("Profile cannot be confirmed without evidenced facts")
    if any(not fact.evidence_text.strip() for fact in resume.facts):
        raise ValueError("Every profile fact must include evidence")
    for fact in resume.facts:
        fact.confirmed = True
    resume.confirmed = True
    session.add(
        AuditEvent(
            event_type="resume.confirmed",
            entity_type="resume_version",
            entity_id=resume.id,
            details={"fact_count": len(resume.facts)},
        )
    )
