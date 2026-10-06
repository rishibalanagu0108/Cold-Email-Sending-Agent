from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from outreach.models import AuditEvent, ProfileFact, ResumeVersion
from outreach.resume import FactInput, confirm_profile, import_resume, replace_profile_facts


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as stream:
        writer.write(stream)


def test_resume_is_versioned_locally_and_idempotently(session: Session, tmp_path: Path) -> None:
    source = tmp_path / "candidate.pdf"
    _blank_pdf(source)

    first = import_resume(session, source, tmp_path / "private")
    second = import_resume(session, source, tmp_path / "private")
    session.commit()

    assert first.id == second.id
    assert Path(first.local_path).is_file()
    assert Path(first.local_path).parent.name == "resumes"
    assert session.scalars(select(ResumeVersion)).all() == [first]
    assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "resume.imported"))


def test_profile_requires_evidence_before_confirmation(session: Session, tmp_path: Path) -> None:
    source = tmp_path / "candidate.pdf"
    _blank_pdf(source)
    resume = import_resume(session, source, tmp_path / "private")

    replace_profile_facts(
        session,
        resume,
        [
            FactInput(
                category="achievement",
                key="latency_reduction",
                value="Reduced latency by 35%",
                evidence_text="Reduced model inference latency by 35%",
                page_number=1,
            )
        ],
    )
    confirm_profile(session, resume)
    session.commit()

    fact = session.scalar(select(ProfileFact))
    assert resume.confirmed is True
    assert fact is not None and fact.confirmed is True
    assert fact.page_number == 1


def test_non_pdf_is_rejected(session: Session, tmp_path: Path) -> None:
    source = tmp_path / "candidate.pdf"
    source.write_text("not a PDF", encoding="utf-8")

    with pytest.raises(ValueError, match="PDF header"):
        import_resume(session, source, tmp_path / "private")
