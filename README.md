# AI Job Outreach

A local, approval-first workflow for finding suitable AI roles with Codex CLI, preparing evidence-backed cold emails, and sending only messages you explicitly approve.

## Safety model

- Codex prepares candidates; it cannot approve or send them.
- Only verified professional addresses can become sendable.
- Every personalized claim must point to resume, job, or company evidence.
- Neon enforces durable deduplication, cooldowns, and suppression.
- Gmail sends only after a dashboard action; tests never contact Gmail.
- There is no scheduler, automated follow-up, job-form submission, CSV flow, or embedded LLM API.

## Local setup

Prerequisites: Python 3.12+, `uv`, a Neon PostgreSQL database, a Gmail account with two-step verification and an app password, and a PDF resume.

```bash
git clone git@github.com:rishibalanagu0108/Cold-Email-Sending-Agent.git
cd Cold-Email-Sending-Agent
uv sync --extra dev
cp .env.example .env
```

Edit `.env` locally. Never paste its values into chat or commit it. The required variables are:

```env
DATABASE_URL=postgresql+psycopg://user:password@host/database?sslmode=require
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=your-app-password
RESUME_PATH=/absolute/path/to/resume.pdf
```

Initialize the database and import the resume:

```bash
uv run alembic upgrade head
uv run outreach resume import /absolute/path/to/resume.pdf
uv run outreach status
uv run outreach serve
```

Open `http://127.0.0.1:8000/setup`, add or correct the evidence-backed profile facts, and confirm the profile.

## Prepare an outreach batch

Open Codex CLI at the repository root and ask it to follow `CODEX_RUNBOOK.md`. The deterministic application commands used by that runbook are:

```bash
uv run outreach prepare-context --limit 20 --output .local/run-context.json
uv run outreach bundle validate .local/preparation-bundle.json
uv run outreach bundle import .local/preparation-bundle.json
```

Then open `http://127.0.0.1:8000/review`. Review and approve drafts individually before using **Send approved batch**. Use **Sync Gmail replies** from the history page to update response and suppression status.

## Development checks

```bash
uv run ruff check src migrations tests
uv run pytest -q
```

## Document order

1. `SPEC.md` — approved product behavior and acceptance criteria
2. `ARCHITECTURE.md` — proposed technical design and trust boundaries
3. `.genesis/PLAN.md` — generated requirement-to-task implementation plan
4. `CODEX_RUNBOOK.md` — repeatable workflow for each future batch
5. `CODEX_BUILD_PROMPT.md` — prompt for a fresh Codex implementation session
6. `AGENTS.md` — repository operating rules

## Current status

The specification and implementation plan are approved. Implementation is tracked in Genesis and is not considered complete while a mandatory gate remains pending.

The real resume and secrets are intentionally absent from the repository.
