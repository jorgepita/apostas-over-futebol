# Claude Instructions

This repository contains a complete documentation system under `/docs`. That documentation is the authoritative source of project knowledge. Conversation history is not.

Every new session should begin by reading the documentation. Only then analyse or implement changes.

---

## Startup Workflow

At the start of every session, in this order:

1. Read `docs/README.md` — it explains the documentation structure and reading order.
2. Follow the documented reading order in `docs/README.md`.
3. Read `docs/07_Current_Status.md` — current development focus and next priorities.
4. Read `docs/05_Known_Issues.md` — open issues with confirmed root causes and fix strategies.
5. Read the most recent file inside `docs/handovers/` if one exists — it records what the previous session completed and what comes next.
6. Only then begin analysing or implementing changes.

Do not infer architecture, design decisions, or development state from previous conversations. If the documentation and a prior conversation conflict, trust the documentation.

---

## Before Making Changes

Before modifying any code:

- Read the relevant sections of `docs/03_Dashboard.md` (frontend) or `docs/04_Backend.md` (backend).
- Check `docs/09_Architecture_Decisions.md` for ADRs that constrain the approach.
- Verify that the issue is not already diagnosed in `docs/05_Known_Issues.md`.
- Understand the existing implementation before proposing changes.
- Prefer extending existing implementations over creating new parallel ones.
- Avoid unnecessary refactoring outside the scope of the task.

---

## During Development

Follow the engineering standards in `docs/DEVELOPMENT_GUIDELINES.md`.

Respect every Architecture Decision Record in `docs/09_Architecture_Decisions.md`. Do not introduce changes that contradict an ADR without explicitly explaining why the reasoning documented there no longer applies.

---

## Documentation Responsibilities

Whenever a permanent behaviour change is made, update the affected documentation in the same session:

- `docs/01_Architecture.md` — if a component was added, removed, or its role changed
- `docs/03_Dashboard.md` — if the frontend architecture changed
- `docs/04_Backend.md` — if the backend architecture changed
- `docs/02_Data_Flow.md` — if the data pipeline changed structurally
- `docs/09_Architecture_Decisions.md` — if a new architectural decision was made
- `docs/07_Current_Status.md` — whenever the development state changes
- `docs/05_Known_Issues.md` — when an issue is confirmed, updated, or resolved
- `docs/08_Change_Log.md` — when a phase completes

Only update documents affected by the change. Do not duplicate information across documents.

---

## End of Session

Before ending a session:

1. Update all documentation affected by the session's changes.
2. Copy `docs/SESSION_HANDOVER_TEMPLATE.md`, fill it in, and save it as `docs/handovers/handover-YYYY-MM-DD.md`.
3. Commit all changes including the handover document.
4. The next session must be able to begin using the documentation and handover alone, without reading this conversation.

---

## Working Principles

- Fix root causes, not symptoms.
- Prefer evidence over assumptions when debugging.
- Prefer extending existing systems over creating new ones.
- Keep changes as small as practical.
- Preserve a single source of truth for every piece of data.
- Validate that a fix is complete before removing diagnostic instrumentation.
- Keep architecture consistent with the documentation.

---

`CLAUDE.md` is a workflow instruction file. Architecture, implementation details, and design decisions are documented in `/docs`. This file should remain short and stable.
