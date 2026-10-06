from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from outreach.config import Settings, get_settings
from outreach.db import create_database_engine
from outreach.drafts import approve_draft, edit_draft, set_draft_status
from outreach.models import (
    Company,
    Contact,
    ContactVerification,
    Draft,
    DraftClaim,
    Job,
    JobMatch,
    MatchEvidence,
    OutreachMessage,
    ProfileFact,
    ResumeVersion,
    Suppression,
)
from outreach.resume import FactInput, confirm_profile, import_resume

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")


def create_app(engine: Engine | None = None, settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    app = FastAPI(title="AI Job Outreach", docs_url=None, redoc_url=None)
    app.state.engine = engine or create_database_engine(configured.database_url)
    app.state.settings = configured
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    def database(request: Request) -> Generator[Session, None, None]:
        with Session(request.app.state.engine) as session:
            yield session

    @app.middleware("http")
    async def reject_cross_origin_posts(request: Request, call_next):
        if (
            request.method == "POST"
            and (origin := request.headers.get("origin"))
            and origin.rstrip("/") != str(request.base_url).rstrip("/")
        ):
            return HTMLResponse("Cross-origin request rejected", status_code=403)
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/review", status_code=303)

    @app.get("/status")
    def status(request: Request, session: Session = Depends(database)) -> dict:
        resume = session.scalar(
            select(ResumeVersion).order_by(ResumeVersion.created_at.desc()).limit(1)
        )
        settings = request.app.state.settings
        return {
            "database": "ready",
            "resume": "confirmed" if resume and resume.confirmed else "needs_setup",
            "gmail": (
                "configured"
                if settings.gmail_address and settings.gmail_app_password
                else "needs_setup"
            ),
            "host": settings.app_host,
        }

    @app.get("/setup", response_class=HTMLResponse)
    def setup(request: Request, session: Session = Depends(database)) -> HTMLResponse:
        resume = session.scalar(
            select(ResumeVersion).order_by(ResumeVersion.created_at.desc()).limit(1)
        )
        facts = (
            session.scalars(
                select(ProfileFact).where(ProfileFact.resume_version_id == resume.id)
            ).all()
            if resume
            else []
        )
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"resume": resume, "facts": facts, "settings": request.app.state.settings},
        )

    @app.post("/setup/resume")
    def upload_resume(
        request: Request,
        resume_file: UploadFile = File(...),
        session: Session = Depends(database),
    ) -> RedirectResponse:
        if not resume_file.filename or not resume_file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "A PDF resume is required")
        upload_dir = request.app.state.settings.local_data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        temporary = upload_dir / "resume-upload.pdf"
        with temporary.open("wb") as stream:
            shutil.copyfileobj(resume_file.file, stream)
        try:
            import_resume(session, temporary, request.app.state.settings.local_data_dir)
            session.commit()
        finally:
            temporary.unlink(missing_ok=True)
        return RedirectResponse("/setup", status_code=303)

    @app.post("/setup/resume/{resume_id}/facts")
    def add_fact(
        resume_id: str,
        category: str = Form(...),
        key: str = Form(...),
        value: str = Form(...),
        evidence_text: str = Form(...),
        page_number: int | None = Form(None),
        session: Session = Depends(database),
    ) -> RedirectResponse:
        resume = session.get(ResumeVersion, resume_id)
        if not resume:
            raise HTTPException(404, "Resume not found")
        fact = FactInput(category, key, value, evidence_text, page_number)
        resume.facts.append(
            ProfileFact(
                category=fact.category.strip(),
                key=fact.key.strip(),
                value=fact.value.strip(),
                evidence_text=fact.evidence_text.strip(),
                page_number=fact.page_number,
            )
        )
        resume.confirmed = False
        session.commit()
        return RedirectResponse("/setup", status_code=303)

    @app.post("/setup/resume/{resume_id}/confirm")
    def confirm_resume(resume_id: str, session: Session = Depends(database)) -> RedirectResponse:
        resume = session.get(ResumeVersion, resume_id)
        if not resume:
            raise HTTPException(404, "Resume not found")
        confirm_profile(session, resume)
        session.commit()
        return RedirectResponse("/setup", status_code=303)

    @app.get("/opportunities", response_class=HTMLResponse)
    def opportunities(
        request: Request,
        status_filter: str | None = None,
        minimum_score: int = 0,
        role: str | None = None,
        company: str | None = None,
        session: Session = Depends(database),
    ) -> HTMLResponse:
        statement = (
            select(JobMatch, Job, Company)
            .join(Job, JobMatch.job_id == Job.id)
            .join(Company, JobMatch.company_id == Company.id)
            .where(JobMatch.fit_score >= minimum_score)
            .order_by(JobMatch.created_at.desc())
        )
        if status_filter:
            statement = statement.where(JobMatch.status == status_filter)
        if role:
            statement = statement.where(Job.normalized_title.contains(role.lower()))
        if company:
            statement = statement.where(Company.name.contains(company))
        rows = session.execute(statement).all()
        return templates.TemplateResponse(request, "opportunities.html", {"rows": rows})

    @app.get("/review", response_class=HTMLResponse)
    def review_queue(request: Request, session: Session = Depends(database)) -> HTMLResponse:
        rows = session.execute(
            select(Draft, JobMatch, Job, Company, Contact)
            .join(JobMatch, Draft.job_match_id == JobMatch.id)
            .join(Job, JobMatch.job_id == Job.id)
            .join(Company, JobMatch.company_id == Company.id)
            .join(Contact, Draft.contact_id == Contact.id)
            .where(Draft.status.in_(["pending_review", "deferred", "approved"]))
            .order_by(Draft.created_at.desc())
        ).all()
        return templates.TemplateResponse(request, "review_queue.html", {"rows": rows})

    @app.get("/review/{draft_id}", response_class=HTMLResponse)
    def review_detail(
        draft_id: str, request: Request, session: Session = Depends(database)
    ) -> HTMLResponse:
        row = session.execute(
            select(Draft, JobMatch, Job, Company, Contact)
            .join(JobMatch, Draft.job_match_id == JobMatch.id)
            .join(Job, JobMatch.job_id == Job.id)
            .join(Company, JobMatch.company_id == Company.id)
            .join(Contact, Draft.contact_id == Contact.id)
            .where(Draft.id == draft_id)
        ).one_or_none()
        if not row:
            raise HTTPException(404, "Draft not found")
        draft, match, job, company, contact = row
        evidence = session.scalars(
            select(MatchEvidence).where(MatchEvidence.job_match_id == match.id)
        ).all()
        claims = session.scalars(select(DraftClaim).where(DraftClaim.draft_id == draft.id)).all()
        verification = session.scalar(
            select(ContactVerification)
            .where(ContactVerification.contact_id == contact.id)
            .order_by(ContactVerification.verified_at.desc())
            .limit(1)
        )
        return templates.TemplateResponse(
            request,
            "review_detail.html",
            {
                "draft": draft,
                "match": match,
                "job": job,
                "company": company,
                "contact": contact,
                "verification": verification,
                "evidence": evidence,
                "claims": claims,
            },
        )

    @app.post("/drafts/{draft_id}/edit")
    def update_draft(
        draft_id: str,
        subject: str = Form(...),
        body: str = Form(...),
        session: Session = Depends(database),
    ) -> RedirectResponse:
        try:
            edit_draft(session, draft_id, subject=subject, body=body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(f"/review/{draft_id}", status_code=303)

    @app.post("/drafts/{draft_id}/approve")
    def approve(draft_id: str, session: Session = Depends(database)) -> RedirectResponse:
        try:
            approve_draft(session, draft_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(f"/review/{draft_id}", status_code=303)

    @app.post("/drafts/{draft_id}/{status}")
    def change_status(
        draft_id: str, status: str, session: Session = Depends(database)
    ) -> RedirectResponse:
        try:
            set_draft_status(session, draft_id, status)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse("/review", status_code=303)

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request, session: Session = Depends(database)) -> HTMLResponse:
        messages = session.scalars(
            select(OutreachMessage).order_by(OutreachMessage.created_at.desc())
        ).all()
        return templates.TemplateResponse(request, "history.html", {"messages": messages})

    @app.get("/suppressions", response_class=HTMLResponse)
    def suppressions(request: Request, session: Session = Depends(database)) -> HTMLResponse:
        rows = session.scalars(select(Suppression).order_by(Suppression.created_at.desc())).all()
        return templates.TemplateResponse(request, "suppressions.html", {"rows": rows})

    return app
