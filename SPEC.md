# Product specification — AI Job Outreach

> Status: draft. A coding agent must not implement product code until this specification is explicitly approved through Genesis.

## 1. Product summary

AI Job Outreach is a single-user, local web application supported by a manually operated Codex CLI workflow. It discovers recent AI-related vacancies, matches them to the user's resume, researches each company and a suitable professional contact, creates evidence-grounded cold-email drafts, and places those drafts in an approval queue. Only the user can approve and initiate sending through Gmail.

The MVP optimizes for relevance, factual accuracy, deduplication, and control—not maximum outreach volume.

## Problem

Finding suitable AI roles and writing genuinely specific outreach is repetitive and error-prone. A useful workflow must:

- avoid rediscovering the same jobs and repeatedly contacting the same company;
- reject roles that do not fit the user's demonstrated experience or location eligibility;
- identify the right type of contact for the company's stage;
- fail closed when an email address cannot be verified;
- understand the company and explain where the user fits;
- use only truthful, traceable resume metrics and company facts;
- let the user review and edit everything before an external email is sent; and
- retain a durable outreach history across future Codex sessions.

“No wrong emails” cannot be guaranteed by any discovery service. Here it means the system never sends unless the address passes the defined verification gate and the user explicitly approves the final recipient and content.

## Users

- Primary user: one job seeker pursuing AI-related roles.
- Email recipients: founders, co-founders, CTOs, engineering leaders, recruiters, and hiring managers contacted at professional addresses.
- Companies: organizations whose public job and company information is researched and stored.

## 4. Goals and success measures

- G-1: Produce a reviewable queue of no more than 20 high-fit companies per manual Codex run.
- G-2: Send zero messages without explicit user approval.
- G-3: Send zero messages to contacts whose verification status is not `verified`.
- G-4: Prevent duplicate job ingestion and premature repeat company outreach across future runs.
- G-5: Make every personalized claim auditable to resume, job-description, or company-source evidence.

## 5. MVP workflow

### 5.1 One-time setup

1. The user supplies the PDF resume in application settings.
2. The system extracts name, email, phone, LinkedIn, GitHub, portfolio, projects, skills, work history, education, and quantified achievements.
3. The dashboard shows extracted sender information and links for correction and confirmation.
4. The user configures `DATABASE_URL`, Gmail address, and Gmail app password in `.env`.
5. The system verifies database connectivity and Gmail configuration without displaying or persisting secret values.

### 5.2 Manual Codex preparation run

1. The user opens Codex CLI in the repository and invokes the documented preparation workflow.
2. Codex reads the confirmed resume profile and prior database state.
3. Codex searches legally accessible sources for AI-related jobs posted within the previous seven days.
4. Codex normalizes and deduplicates jobs and companies before doing expensive research.
5. Codex evaluates role fit and retains no more than 20 distinct eligible companies.
6. For each retained company, Codex selects the strongest matching role, researches the company, identifies the appropriate contact type, and finds a professional email.
7. The address is checked through public evidence and/or an available free verification service. Invalid, risky, unknown, unverifiable, or unsupported catch-all addresses are not sendable.
8. Codex creates a factual, personalized draft and an evidence map.
9. Validated records are stored in Neon with status `pending_review`; rejected and skipped candidates retain a reason.

### 5.3 Review and sending

1. The user reviews each opportunity, source, fit explanation, contact, verification evidence, subject, body, and attachment.
2. The user may edit, approve, reject, or defer a draft.
3. Approval records the exact recipient, subject, body, resume version, and timestamp.
4. The user initiates `Send approved batch`; no scheduled or background send exists in the MVP.
5. A batch contains at most 20 approved drafts and sends sequentially with conservative pacing.
6. Success or failure is recorded per message. A partial failure must not resend successful messages.

### 5.4 Reply synchronization and suppression

1. The user manually invokes reply synchronization from the dashboard.
2. The system reads only Gmail data needed to match replies to sent outreach.
3. A reply marks the outreach as `replied` and prevents further outreach to that company unless the user explicitly overrides it.
4. Rejection, opt-out, or “do not contact” language permanently suppresses the recipient and company.

## Functional requirements

### Resume and profile

- FR-1: The system shall accept a user-selected PDF resume and keep the file on the local machine.
- FR-2: The system shall extract structured profile data and retain the source text or page reference supporting every extracted skill, link, experience item, and numerical achievement.
- FR-3: The user shall be able to review and edit extracted sender details and professional links before use.
- FR-4: Each resume replacement shall create a version; every draft and sent message shall reference the resume version used.

### Discovery and eligibility

- FR-5: A manual Codex run shall process no more than 20 distinct eligible companies.
- FR-6: Discovery shall cover legally accessible official career pages and other accessible job sources, prioritizing the official job posting as canonical.
- FR-7: The default freshness window shall be seven days and shall be configurable.
- FR-8: Included role families shall cover AI Engineer, Machine Learning Engineer, Applied AI Engineer, Generative AI/LLM Engineer, Agentic AI Engineer, NLP Engineer, Computer Vision Engineer, AI Research Engineer, MLOps/ML Platform Engineer, and closely related roles when resume evidence supports the fit.
- FR-9: Seniority shall be inferred from the confirmed resume profile; clearly over-senior roles shall be rejected with a reason.
- FR-10: Remote roles may be worldwide. Onsite or hybrid roles outside the user's home-work eligibility shall require explicit relocation or visa-sponsorship evidence.
- FR-11: Unpaid, deceptive, unrelated, closed, or unconfirmed listings shall be excluded.
- FR-12: The system shall store rejected candidates and machine-readable rejection reasons.

### Matching and company research

- FR-13: Each retained role shall receive a transparent 0–100 fit score with default weighting: role alignment 35, demonstrated skills 30, experience/seniority 20, location eligibility 10, and evidence quality 5.
- FR-14: A role below the default score of 70 shall not enter the review queue unless the user changes the threshold.
- FR-15: The fit explanation shall identify requirements met, partial gaps, disqualifying gaps, and resume evidence.
- FR-16: Company research shall include product or mission, a relevant current initiative or technical need when publicly supported, company stage/size estimate, and why the user's evidence is relevant.
- FR-17: Every company claim shall cite a source URL and retrieval timestamp. A draft requires the job description plus at least one credible company source.
- FR-18: The workflow shall never invent company initiatives, recipient relationships, achievements, skills, metrics, or experience.

### Deduplication

- FR-19: Companies shall be canonically identified by normalized root domain, with explicit aliases for rebrands and subsidiaries.
- FR-20: Jobs shall be deduplicated by canonical company plus source job identifier or canonical URL; otherwise a normalized title/location/description fingerprint shall be used.
- FR-21: Multiple matching roles at one company shall produce one candidate centered on its highest-fit role.
- FR-22: A successfully contacted company shall be ineligible for 90 days.
- FR-23: After 90 days, a company may be reconsidered only for a distinct, newly posted role whose reconsideration reason is stored.
- FR-24: Any reply suppresses further automated eligibility. Rejection or opt-out permanently suppresses recipient and company unless the user deliberately removes the suppression.
- FR-25: Re-running an interrupted import or send with the same idempotency key shall not create another job, draft, approval, or sent message.

### Contact selection and verification

- FR-26: Contact priority shall be: early-stage startup → founder/co-founder; medium company → CTO or relevant engineering leader; large company → role-relevant recruiter/hiring manager or engineering leader.
- FR-27: Only professional/company addresses may be used, except an address publicly designated by the person for professional contact.
- FR-28: The MVP may use public sources and free service tiers only.
- FR-29: A contact shall store source URLs, discovery method, verification provider/method, verification timestamp, and status.
- FR-30: Only `verified` is sendable. `unverified`, `unknown`, `risky`, `invalid`, and unsupported `catch_all` states fail closed.
- FR-31: If no verified contact exists, skip the company with reason `no_verified_contact`; guessed addresses shall never be sendable.

### Draft generation

- FR-32: Each candidate shall include an editable subject and plain-text email body.
- FR-33: The default email shall be professional, direct, human-sounding, and 120–180 words.
- FR-34: The email shall connect one specific company or role need to two or three demonstrated resume strengths, favoring truthful numerical achievements when available.
- FR-35: Every nontrivial claim shall have an evidence-map entry linking it to resume, job, or company-source evidence.
- FR-36: The email shall include a concise invitation to discuss the role, confirmed professional links, and the current resume PDF attachment.
- FR-37: The MVP shall send one initial email only and shall not generate or send follow-ups.
- FR-38: A formal opt-out sentence is not required, but reply classification and suppression remain mandatory.

### Dashboard and approval

- FR-39: The local application shall provide setup, opportunities, review queue, outreach history, suppressions, and system-status views.
- FR-40: A review item shall show role and company sources, score breakdown, fit/gap analysis, company research, contact role, address, verification evidence, subject, body, links, and resume version.
- FR-41: The user shall be able to edit, approve, reject, defer, and bulk-select only individually reviewed sendable drafts.
- FR-42: Approval shall be impossible unless the address is verified, required sources exist, evidence checks pass, and a resume version is attached.
- FR-43: Changing recipient, subject, body, or resume after approval shall invalidate approval.
- FR-44: The dashboard shall bind only to `127.0.0.1` by default and require no login in the MVP.

### Gmail delivery and replies

- FR-45: Gmail credentials shall be read from environment variables and never written to Neon, generated files, logs, or client-side code.
- FR-46: Sending shall occur only after a user action and include no more than 20 approved drafts per batch.
- FR-47: Messages shall send sequentially with configurable conservative pacing, defaulting to at least 30 seconds between attempts.
- FR-48: Each attempt shall use a durable idempotency key and store Gmail message ID, timestamp, status, and sanitized error data.
- FR-49: An ambiguous delivery outcome shall become `delivery_unknown` and block automatic retry until Gmail Sent Mail is reconciled.
- FR-50: A manual reply-sync action shall match Gmail threads/messages to outreach and update response and suppression state.

### Data

- FR-51: Neon PostgreSQL shall be the system of record for structured profile metadata, jobs, companies, sources, contacts, verification results, drafts, approvals, outreach, replies, suppressions, runs, and audit events.
- FR-52: Resume binary and Gmail secret shall remain local; only resume version identity and non-secret extracted profile data may be stored in Neon.
- FR-55: The dashboard shall filter by run, status, date, score, role family, company, and rejection reason.

### Codex interoperability

- FR-56: The repository shall contain a self-contained Codex runbook for discovery, research, evidence, validation, import, and recovery.
- FR-57: The application shall expose deterministic validation/import for a versioned JSON preparation bundle; invalid bundles shall fail atomically with field-level errors.
- FR-58: The bundle shall carry a run ID, sources, timestamps, canonical identities, score components, evidence maps, verification, and draft content.
- FR-59: Importing a bundle shall never approve or send email.
- FR-60: Codex shall check prior company, job, outreach, reply, and suppression records before researching or drafting.

## 7. Required state and data model

Draft lifecycle:

`discovered → researched → pending_review → approved → sending → sent`

Alternative terminal or holding states are `rejected`, `deferred`, `skipped`, `failed`, `delivery_unknown`, `replied`, and `suppressed`. Only `pending_review` may become `approved`; only `approved` may become `sending`; only a confirmed Gmail response may become `sent`. Content changes return an approved item to `pending_review`.

Minimum durable entities:

- `resume_versions` and `profile_facts`
- `discovery_runs`
- `companies` and `company_aliases`
- `jobs`, `job_sources`, `job_matches`, and `match_evidence`
- `contacts` and `contact_verifications`
- `drafts`, `draft_claims`, and `approvals`
- `send_batches` and `outreach_messages`
- `replies`, `suppressions`, and `audit_events`

The implementation may consolidate tables when constraints and auditability remain intact; it must not add speculative abstractions.

## Non-functional requirements

- NFR-1: Missing verification, missing evidence, stale approval, missing attachment, or ambiguous state shall block sending.
- NFR-2: Every external side effect shall require an explicit user action and current approval.
- NFR-3: Database uniqueness constraints and idempotency keys shall enforce deduplication, not UI checks alone.
- NFR-4: Secrets and full Gmail message bodies shall be redacted from logs and error reports.
- NFR-5: Database traffic shall use TLS. `.env` and resume files shall be excluded from version control.
- NFR-6: Job text, web content, email bodies, and imported JSON are untrusted data, never executable instructions; prompt injection shall not override the runbook or approval boundary.
- NFR-7: User-visible content shall be escaped or sanitized, and external URLs shall allow only `http` and `https`.
- NFR-8: Importing 20 companies shall commit fully or fail without partial duplicate creation.
- NFR-9: System status shall report database, resume, Gmail, and reply-sync readiness without exposing credentials.
- NFR-10: Store timestamps in UTC and display Asia/Kolkata by default.
- NFR-11: Critical flows shall support keyboard navigation, visible focus, semantic labels, and readable contrast.
- NFR-12: Use the smallest stack compatible with the user's resume, Neon, Gmail SMTP/IMAP, local execution, migrations, and automated tests. Final stack selection waits for the resume.

## Constraints

- No embedded LLM API is available in the MVP.
- No automatic schedule exists. The user starts every Codex run and send action.
- Discovery uses accessible public sources and free service tiers only. It must not bypass logins, paywalls, CAPTCHAs, robots controls, rate limits, or source terms.
- Gmail address, app password, and Neon connection string live in `.env` and appear in committed files only as placeholders.
- The dashboard is trusted only on the user's computer and must not bind publicly by default.
- Neon may hold the structured professional data described in FR-51 and FR-52.
- Email and privacy rules vary by jurisdiction. The MVP sends narrowly targeted, individually approved employment inquiries, respects suppression, and does not claim universal legal compliance.
- The resume is unavailable during specification; no resume fact, metric, identity, link, or stack expertise may be invented.

## Non-goals

- Automatic job-form applications.
- Autonomous or scheduled discovery, drafting, approval, or sending.
- Automated follow-up sequences.
- More than one initial email per company within the eligibility rules.
- Paid job, enrichment, verification, or AI services.
- Bypassing source access controls or terms.
- Hosted/public access, multiple users, teams, or role-based access.
- A general-purpose applicant tracking system.
- Guaranteed delivery, replies, interviews, employment, or perfect contact data.
- Claims or numbers unsupported by captured evidence.

## Acceptance criteria

- AC-1: Given a resume PDF, the user can confirm extracted identity, links, skills, experience, and metrics, and the saved version retains evidence references.
- AC-2: A bundle containing more than 20 eligible companies is rejected before import.
- AC-3: Importing the same valid bundle twice creates no duplicate run result, company, job, contact, or draft.
- AC-4: Two listings for the same canonical job resolve to one job with multiple sources.
- AC-5: Multiple roles at one company yield one candidate containing the highest-fit primary role.
- AC-6: A company contacted fewer than 90 days ago is rejected before contact research unless the user overrides it.
- AC-7: After 90 days, the company is still rejected unless a distinct new role and reconsideration reason exist.
- AC-8: A replied or permanently suppressed company cannot enter a sendable state.
- AC-9: A stale, over-senior, closed, unpaid, unrelated, or location-ineligible role is excluded with a stored reason under defaults.
- AC-10: Every queued candidate shows a score whose components total the result and cites resume and job evidence.
- AC-11: Every queued draft has the job description, one company source, timestamps, and evidence mappings.
- AC-12: An unsupported claim blocks import or approval and identifies the correction required.
- AC-13: A contact whose state is not `verified` cannot be approved or sent.
- AC-14: A guessed pattern, unsupported catch-all result, or absent/stale verification cannot pass the send gate.
- AC-15: Editing an approved recipient, subject, body, or resume invalidates approval.
- AC-16: Without explicit current approval, neither CLI import nor dashboard endpoints can create a Gmail attempt.
- AC-17: A user-triggered batch sends at most 20 approved messages sequentially and records each result.
- AC-18: Repeating a send request with the same idempotency key does not resend a successful message.
- AC-19: An ambiguous Gmail outcome becomes `delivery_unknown` and is not retried automatically.
- AC-20: Manual reply sync associates a test reply, marks it `replied`, and blocks future company eligibility.
- AC-21: A test opt-out or rejection creates permanent suppression enforced by discovery, import, and sending.
- AC-23: Secret-scanning tests show Gmail and Neon secrets are absent from client bundles, logs, and fixtures.
- AC-24: The dashboard listens on `127.0.0.1` and its critical review/approval flow is keyboard accessible.
- AC-25: The repository contains `.env.example` placeholders, a resume-safe local path convention, and no real secret or resume.
- AC-26: A fresh Codex session can use the runbook to prepare and atomically import a valid evidence bundle without an external LLM API.

## Risks

- Incorrect recipient: require professional-source evidence, strict verification, visible review, and approval.
- Hallucinated personalization: require claim-level evidence and block unsupported claims.
- Duplicate or spam-like outreach: enforce database uniqueness, 90-day suppression, no follow-ups, and batch limits.
- Gmail restriction: send sequentially, pace conservatively, stop on quota/auth errors, and do not auto-retry ambiguity.
- Prompt injection: treat retrieved text as untrusted data and keep workflow instructions separate.
- Source-policy violation: use official/access-permitted pages, respect limits, and never bypass controls.
- Secret or personal-data leakage: local environment secrets and resume, redacted logs, TLS, and Git exclusions.
- Incorrect company merging: show canonical domain and aliases during review and permit correction.
- Stale jobs: record retrieval time and recheck that the role is open before approval/send.
- Scope creep: manual Codex operation, local single-user dashboard, one initial email, free services, and no scheduler.

## Open questions

- Exact stack: select after the actual resume is available, favoring technologies the user can maintain while satisfying NFR-12.
- Specific free verification providers: use adapters only where current free terms and API access are confirmed during implementation; public verification is the fallback.
- Exact sender identity, signature, links, phone, and resume path: extract from the actual resume and require confirmation during setup.

These setup-time choices do not alter the approval, evidence, verification, deduplication, or sending boundaries.
