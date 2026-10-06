from __future__ import annotations

import json
import stat
from pathlib import Path

from pypdf import PdfWriter
from sqlalchemy import LargeBinary
from sqlalchemy.orm import Session

from outreach.context import build_preparation_context
from outreach.local_files import write_private_text
from outreach.models import ProfileFact, ResumeVersion
from outreach.resume import import_resume


def _pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as stream:
        writer.write(stream)


def test_resume_binary_stays_in_private_local_storage(session: Session, tmp_path: Path) -> None:
    source = tmp_path / "resume.pdf"
    _pdf(source)
    version = import_resume(session, source, tmp_path / ".local")
    session.commit()

    stored = Path(version.local_path)
    assert stored.is_file()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert stat.S_IMODE(stored.parent.stat().st_mode) == 0o700
    assert not any(
        isinstance(column.type, LargeBinary) for column in ResumeVersion.__table__.columns
    )


def test_codex_context_is_private_and_excludes_local_path(session: Session, tmp_path: Path) -> None:
    resume = ResumeVersion(
        sha256="9" * 64,
        original_filename="resume.pdf",
        local_path=str(tmp_path / "private.pdf"),
        confirmed=True,
    )
    resume.facts.append(
        ProfileFact(
            category="skill",
            key="python",
            value="Python",
            evidence_text="Python",
            confirmed=True,
        )
    )
    session.add(resume)
    session.commit()
    output = tmp_path / ".local" / "context.json"
    write_private_text(output, json.dumps(build_preparation_context(session)))

    content = output.read_text(encoding="utf-8")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert "local_path" not in content
    assert str(tmp_path) not in content
    assert "gmail" not in content.lower()


def test_repository_ignores_runtime_secrets_and_resume_files() -> None:
    entries = set(Path(".gitignore").read_text(encoding="utf-8").splitlines())
    assert {".env", ".local/", "*.pdf"} <= entries
