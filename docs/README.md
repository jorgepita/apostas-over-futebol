# Documentation Index

The `/docs` directory contains the authoritative documentation for the Football Bot project. Treat these documents as the single source of project knowledge. Do not rely on previous conversations for architectural decisions, implementation details, or project status — the answer is in this directory.

---

## Documentation Structure

```
docs/
├── README.md                     ← Start here. Explains the documentation system.
├── PROJECT_MAP.md                ← Repository navigation guide: where everything lives.
├── 00_Project_Context.md         ← What the system is, design principles, constraints.
├── 01_Architecture.md            ← Component map: every file, service, and role.
├── 02_Data_Flow.md               ← How data moves from generation to the browser.
├── 03_Dashboard.md               ← Frontend technical reference.
├── 04_Backend.md                 ← Backend technical reference.
├── 05_Known_Issues.md            ← Open issues: symptoms, root cause, fix strategy.
├── 06_Roadmap.md                 ← Planned future work with priorities and dependencies.
├── 07_Current_Status.md          ← Snapshot of the project right now.
├── 08_Change_Log.md              ← Completed phases in reverse chronological order.
├── 09_Architecture_Decisions.md  ← Why key decisions were made (ADR repository).
├── DEVELOPMENT_GUIDELINES.md     ← Development standards: how to implement changes correctly.
├── SESSION_HANDOVER_TEMPLATE.md  ← Reusable template for end-of-session handovers.
└── handovers/                    ← Filled handover documents, one per session.
```

`SESSION_HANDOVER_TEMPLATE.md` is never edited. Copy it at the end of each session, fill it in, and save the result in `docs/handovers/`.

---

## Reading Order

Read in this order to build a complete mental model before making any implementation suggestion or change.

| # | Document | Why it exists |
|---|---|---|
| 1 | [00_Project_Context.md](00_Project_Context.md) | What the system is, what it does, and the design principles that govern all decisions. Read this first. |
| 2 | [09_Architecture_Decisions.md](09_Architecture_Decisions.md) | Why the system is built the way it is. Every ADR explains a decision that should not be reversed without good reason. Read this before proposing any structural change. |
| 3 | [01_Architecture.md](01_Architecture.md) | Component map: every file, service, and data flow in one place. |
| 4 | [PROJECT_MAP.md](PROJECT_MAP.md) | Repository navigation guide: where every file and directory lives and when to edit them. |
| 5 | [02_Data_Flow.md](02_Data_Flow.md) | How data moves from pick generation through to the browser, including settlement. |
| 6 | [03_Dashboard.md](03_Dashboard.md) | Frontend technical reference: global state, rendering model, localStorage, page-by-page behaviour. |
| 7 | [04_Backend.md](04_Backend.md) | Backend technical reference: Railway service, GitHub integration, pick generation, settlement engine, league registry. |
| 8 | [07_Current_Status.md](07_Current_Status.md) | What is working now, what is under development, and what the next priorities are. Read this before making implementation suggestions. |
| 9 | [05_Known_Issues.md](05_Known_Issues.md) | Open issues with full diagnosis, fix strategy, and validation checklist. Check this before proposing a fix. |
| 10 | [06_Roadmap.md](06_Roadmap.md) | Planned future work, with priorities and dependencies. |
| 11 | [08_Change_Log.md](08_Change_Log.md) | Major architectural phases in reverse chronological order. |
| 12 | [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) | Development standards: how to implement changes correctly, debugging workflow, working with Claude. |

---

## Starting a New Conversation

1. Read this README first.
2. Read the documents above in the recommended order before proposing any change.
3. Treat the documentation as authoritative. If the docs and chat history conflict, trust the docs.
4. Do not infer architecture from previous conversation summaries. The implementation details are in `03_Dashboard.md` and `04_Backend.md`.
5. Read `07_Current_Status.md` before making any implementation suggestion — the current development focus and next priorities are recorded there.
6. Check `05_Known_Issues.md` before proposing a fix for any reported problem. The root cause and fix strategy may already be documented.
7. Respect all Architecture Decision Records in `09_Architecture_Decisions.md`. Do not propose reverting a decision without understanding the reasoning documented there.

---

## Development Workflow

Every development session follows this sequence:

1. **Read the documentation.** Start with this README, then the documents in reading order, then `07_Current_Status.md` and `05_Known_Issues.md` for the current state.
2. **Analyse the problem.** Understand the affected components, verify the root cause, and check whether an ADR constrains the fix approach.
3. **Implement the change.** Make the smallest correct change. Do not refactor beyond what the task requires.
4. **Validate.** Run through the relevant checklist in `05_Known_Issues.md` if one exists. Test the affected behaviour manually.
5. **Update documentation.** Update `07_Current_Status.md`, `05_Known_Issues.md`, `08_Change_Log.md`, and any other document that is now out of date.
6. **Complete the session handover.** Copy `SESSION_HANDOVER_TEMPLATE.md`, fill it in, and save it in `docs/handovers/`. Commit everything.

Every session ends with updated documentation. A session that closes without updating the documentation has produced incomplete work.

---

## Session Lifecycle

```
Start session
      │
      ▼
Read README + docs
      │
      ▼
Analyse problem
      │
      ▼
Implement
      │
      ▼
Validate
      │
      ▼
Update documentation
      │
      ▼
Create handover (docs/handovers/handover-YYYY-MM-DD.md)
      │
      ▼
Commit
      │
      ▼
End session
```

The handover document is what makes the next session possible without relying on chat history.

---

## Updating the Documentation

Documentation is divided into three categories based on how often it should change.

### Stable documentation

Reflects permanent decisions and the long-term architecture of the system. Rarely changes. If you find yourself wanting to change one of these files frequently, the change probably belongs in an operational document instead.

- `00_Project_Context.md` — only if the fundamental scope or design principles change
- `01_Architecture.md` — only when a component is added, removed, or its role changes
- `02_Data_Flow.md` — only when the data pipeline changes structurally
- `03_Dashboard.md` — only when the frontend architecture changes
- `04_Backend.md` — only when the backend architecture changes
- `09_Architecture_Decisions.md` — only to accept a new decision or formally supersede an existing one

### Operational documentation

Reflects the current state of active development. Updated whenever required — potentially every session.

- `05_Known_Issues.md` — add new issues as they are confirmed; move resolved issues to `08_Change_Log.md`
- `07_Current_Status.md` — update after any significant change to what is working, what is broken, or what the next priority is
- `08_Change_Log.md` — add a new entry when a phase completes
- `06_Roadmap.md` — update when priorities shift, new ideas are added, or planned work is completed
- `DEVELOPMENT_GUIDELINES.md` — update when a UI or code convention is established or changed

### Session documentation

Generated at the end of each development session. Never modified after the session ends — each handover is a point-in-time record.

- `SESSION_HANDOVER_TEMPLATE.md` — the master template; never edited directly
- `docs/handovers/` — one filled handover per session; provides continuity between sessions

---

## Documentation Rules

- **Keep documentation factual.** Describe what the system does and why decisions were made. Do not speculate or document hypothetical designs.
- **Separate permanent knowledge from temporary information.** Architectural decisions belong in `09_Architecture_Decisions.md`. Active bugs belong in `05_Known_Issues.md`. Do not mix them.
- **Do not duplicate information across documents.** If a fact belongs in `04_Backend.md`, reference it there rather than repeating it in `07_Current_Status.md`.
- **Record architectural decisions in `09_Architecture_Decisions.md`.** Any decision that constrains future implementation choices should be documented as an ADR.
- **Move resolved issues to the Change Log.** When an issue in `05_Known_Issues.md` is fixed, add a phase entry to `08_Change_Log.md` and remove the issue entry.
- **Keep `07_Current_Status.md` focused on the present.** It describes what is true now, not what was true last month or what might be true next month.

---

## Documentation Philosophy

- **Permanent knowledge stays in permanent documents.** Architecture, data flow, and design decisions belong in stable files that change rarely. They should not appear in session handovers or current-status notes.
- **Temporary information stays in temporary documents.** Active bugs, current status, and in-progress work belong in operational files. They should not pollute the stable reference material.
- **Documentation should outlive conversations.** Chat history is transient. When a conversation ends, its context is gone. The documentation is what remains.
- **Documentation is authoritative.** If the documentation and a previous conversation disagree, the documentation is correct. Update the documentation rather than trusting memory.
- **Architecture must never depend on conversation memory.** Any decision significant enough to affect future implementation must be recorded in `09_Architecture_Decisions.md`. If it is only in a chat, it will be forgotten.

---

## Goal

The documentation exists so that any future conversation can understand the project quickly, preserve architectural consistency, and continue development without relying on previous chat history. A conversation that reads these documents in order should be able to make correct implementation decisions without needing access to the original design discussions.
