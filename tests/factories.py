from __future__ import annotations

from datetime import UTC, datetime

from outreach.bundles import PreparationBundle


def candidate_payload(
    *,
    company: str = "Example AI",
    domain: str = "example.ai",
    title: str = "Agentic AI Engineer",
    role_family: str = "agentic_ai_engineer",
    posted_at: datetime | None = None,
    status: str = "eligible",
    rejection_reason: str | None = None,
) -> dict:
    now = datetime.now(UTC)
    body = (
        "Hello Ada, I am reaching out about the Agentic AI Engineer opening at Example AI. "
        "Your focus on reliable AI products closely matches the systems work described in my "
        "resume. I have built Python services, evaluation pipelines, retrieval workflows, and "
        "tool-using agents with careful monitoring and measurable delivery outcomes. I would "
        "bring that practical engineering approach to the role, especially where dependable "
        "automation and clear quality checks matter. My background also includes collaborating "
        "across product and engineering teams, translating ambiguous requirements into tested "
        "features, and improving existing workflows without unnecessary infrastructure. I have "
        "included my resume and portfolio for context. If the position is still active, I would "
        "welcome a short conversation about the problems your team is solving and how my "
        "experience could contribute. Thank you for considering my note. Best regards, Candidate"
    )
    return {
        "company_name": company,
        "company_domain": domain,
        "company_stage": "early",
        "title": title,
        "role_family": role_family,
        "location": "Remote",
        "work_arrangement": "remote",
        "description": "Build production-grade agentic AI systems and evaluation pipelines.",
        "source_name": "company",
        "source_job_id": f"{domain}-{title}",
        "source_url": f"https://{domain}/jobs/ai-engineer",
        "posted_at": (posted_at or now).isoformat() if status == "eligible" else None,
        "is_open": status == "eligible",
        "is_paid": True,
        "location_eligible": True,
        "seniority_eligible": True,
        "status": status,
        "rejection_reason": rejection_reason,
        "score": {
            "role_alignment": 30,
            "demonstrated_skills": 25,
            "experience_seniority": 15,
            "location_eligibility": 10,
            "evidence_quality": 5,
        },
        "evidence": [
            {
                "id": "job-1",
                "evidence_type": "job",
                "claim": "The company is hiring an agentic AI engineer.",
                "source_text": "Agentic AI Engineer",
                "source_url": f"https://{domain}/jobs/ai-engineer",
                "retrieved_at": now.isoformat(),
            },
            {
                "id": "company-1",
                "evidence_type": "company",
                "claim": "The company builds AI products.",
                "source_text": "We build reliable AI products.",
                "source_url": f"https://{domain}/about",
                "retrieved_at": now.isoformat(),
            },
            {
                "id": "resume-1",
                "evidence_type": "resume",
                "claim": "Candidate has matching Python experience.",
                "source_text": "Python",
            },
        ],
        "contact": {
            "name": "Ada Founder",
            "role": "Co-Founder",
            "email": f"ada@{domain}",
            "source_url": f"https://{domain}/team",
            "professional": True,
            "public_professional": False,
            "verification": {
                "status": "verified",
                "method": "official_public",
                "verified_at": now.isoformat(),
                "domain_accepts_mail": True,
                "catch_all": False,
                "evidence_url": f"https://{domain}/team",
                "evidence_excerpt": f"Contact Ada at ada@{domain}",
            },
        },
        "draft": {
            "subject": "Agentic AI Engineer — practical production experience",
            "body": body,
            "professional_links": ["https://github.com/candidate"],
            "claims": [
                {
                    "claim_text": "I have built Python services.",
                    "evidence_ids": ["resume-1"],
                },
                {
                    "claim_text": "Your team is hiring an Agentic AI Engineer.",
                    "evidence_ids": ["job-1", "company-1"],
                },
            ],
        },
    }


def bundle_payload(resume_id: str, candidates: list[dict] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "run_idempotency_key": "run-example-0001",
        "generated_at": datetime.now(UTC).isoformat(),
        "resume_version_id": resume_id,
        "candidates": candidates if candidates is not None else [candidate_payload()],
    }


def make_bundle(resume_id: str, candidates: list[dict] | None = None) -> PreparationBundle:
    return PreparationBundle.model_validate(bundle_payload(resume_id, candidates))
