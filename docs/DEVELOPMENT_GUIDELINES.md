# Development Guidelines

This document defines the development standards used throughout the Football Bot project. It describes **how to implement changes correctly**. For what the system is and why it was designed that way, see `00_Project_Context.md`, `01_Architecture.md`, and `09_Architecture_Decisions.md`.

---

## General Development Principles

- **Fix root causes, not symptoms.** A patch that suppresses an error without correcting the underlying condition will fail again.
- **Keep changes as small as possible.** A focused change is easier to validate, easier to revert, and easier to understand in the change log.
- **Do not refactor beyond the task.** If surrounding code is imperfect but working, leave it. Incidental refactoring breaks stable behaviour and makes regressions harder to attribute.
- **Preserve stable behaviour.** If something is working and the task does not require touching it, do not touch it.
- **Prefer simplicity over cleverness.** A clear implementation is correct more often than a clever one, and easier to maintain.
- **Keep the system deterministic.** The same input should always produce the same output. Avoid randomness, time-sensitive logic, or hidden state that makes behaviour unpredictable.

---

## Before Writing Code

Complete this checklist before beginning any implementation:

- [ ] Read the relevant sections of the documentation (`03_Dashboard.md` for frontend, `04_Backend.md` for backend).
- [ ] Check `05_Known_Issues.md` — the problem and fix strategy may already be documented.
- [ ] Review the relevant ADRs in `09_Architecture_Decisions.md` to confirm the proposed approach does not contradict an established decision.
- [ ] Read the existing implementation before modifying it. Understand what the code actually does, not what it is assumed to do.
- [ ] Do not assume a rewrite is better than a targeted change. The existing implementation encodes constraints that may not be immediately visible.

---

## Debugging Guidelines

Debugging is an evidence-driven process. Changing code speculatively is not debugging — it is guessing, and it produces regressions alongside accidental fixes.

**Workflow**

1. **Reproduce the issue first.** If you cannot reproduce it reliably, you cannot confirm that a fix works. Define the exact steps that trigger the problem before touching any code.
2. **Gather evidence before proposing a fix.** Read the relevant code paths, inspect actual values (console logs, print statements, API responses), and understand what is happening before forming a hypothesis.
3. **Identify the root cause before modifying the implementation.** Fixing a symptom without understanding why it occurs leaves the underlying condition intact. The symptom will return.
4. **Use temporary diagnostics, not speculative code changes.** Add a console log or print statement to confirm a hypothesis. Do not change logic to "see if it helps".
5. **Fix one thing at a time.** Implementing multiple unrelated fixes simultaneously makes it impossible to attribute the resolution to a specific change.
6. **Validate the fix before removing instrumentation.** Run the full validation checklist in `05_Known_Issues.md` before removing diagnostic code. Removing instrumentation before validation closes the observation window.
7. **Remove diagnostics after validation.** Temporary print statements and console logs should not remain in production code. Their removal is part of the fix, not optional cleanup.
8. **Update `05_Known_Issues.md` if the investigation changes the diagnosis.** If the confirmed root cause differs from what was initially documented, update the issue entry before implementing the fix.

---

## Frontend Guidelines

The frontend is a single self-contained HTML file. See ADR-005 for the reasoning.

**Architecture**

- Maintain the single-file architecture. Do not split into separate JS or CSS files.
- Preserve the `rerenderAll()` / sub-render function pattern. All page state is derived from `state` at render time.
- Never read from the DOM to infer application state. Read from `state`.
- Do not add a framework, build step, or module system.

**DOM Access**

- Guard every DOM access. Never assume an element exists. Use `const el = document.getElementById('x'); if (!el) return;` before any operation on `el`.
- Avoid storing DOM references in `state`. Re-query on each render.
- Do not write to the DOM outside of a render function.

**Rendering**

- Avoid duplicated rendering logic. If two pages display the same data, extract a shared helper.
- Never trigger a render from inside a render. Renders are synchronous top-down, not recursive.
- After modifying `state`, call `rerenderAll()` or the relevant page sub-render. Do not patch the DOM directly.

**Localisation**

- Keep all UI text in European Portuguese (PT-PT).
- Do not mix languages in user-facing strings.

**Layout**

- Optimise for desktop (laptop screen, ~1366×768 viewport) while remaining fully responsive on mobile.
- High information density. Avoid large padding, oversized cards, or excessive whitespace.
- Minimise scrolling on each page. Content should be visible without scrolling where possible.

---

## Backend Guidelines

The backend is a stateless Flask service on Railway. See ADR-003 for the reasoning.

**Statelessness**

- Railway holds no state between requests. Every request must read what it needs from GitHub and write back to GitHub. Do not cache data in module-level variables across requests.
- All persistent data lives in GitHub. Do not write to the local filesystem on Railway except for temporary processing (`tempfile.TemporaryDirectory`).

**Configuration**

- Do not hardcode production values (API keys, rate limits, repository coordinates, bankroll amounts). Use environment variables for secrets and `config.json` for model parameters. See ADR-010.
- Add new configurable parameters to `config.json` with a matching `DEFAULT_` constant in `src/config.py`.

**GitHub API**

- Every write to GitHub requires fetching the current SHA first. Do not skip the GET step.
- Handle SHA conflicts explicitly. If a `422` response is received on a PUT, retry with a fresh SHA.
- Prefer the existing `github_request()` helper over raw `requests` calls.

**Reuse before extending**

- Before creating a new helper function, check whether an existing one covers the need.
- Before adding a new endpoint to `sync_server.py`, confirm the operation cannot be done via an existing endpoint.

---

## Data Integrity Rules

- **Never introduce a second source of truth for the same dataset.** `cloud_state.json` is the single source of truth for manual bets. Settlement results, bet objects, and status flags all live there. See ADR-001 and ADR-008.
- **Reuse existing persistence paths.** A new data type should be stored in `cloud_state.json` or a new GitHub-committed file, not in a parallel store.
- **Do not duplicate business logic.** Settlement calculation, profit calculation, and market resolution are implemented once in `update_dataframe()`. See ADR-002 and ADR-009. A second implementation of the same logic will diverge.
- **Validate state transitions.** A manual bet moves through a defined lifecycle (`created → approved → live → settled`). Code that skips or reverses a transition produces inconsistent state.
- **Preserve backwards compatibility.** `cloud_state.json` is read by the browser. Any change to its schema must be backwards-compatible or migrated explicitly.

---

## UI / UX Guidelines

The dashboard should feel like a professional trading terminal or sportsbook control panel — dense, fast, and operational.

- **High information density.** Pack relevant data into the available space. Avoid decorative whitespace.
- **Minimal scrolling.** Each page should present its primary content without requiring a scroll. Use compact tables and cards.
- **Fast workflows.** The most frequent action on each page (approve, settle, view) should require the fewest possible clicks.
- **Compact components.** Prefer small, tight cards over large ones. Avoid oversized buttons. Consistent spacing across pages.
- **No marketing patterns.** Do not use hero sections, large imagery, or layout patterns suited to public-facing websites. This is an internal operational tool.
- **Consistent typography.** Monospace for numbers and financial figures. Body font for labels and descriptions. No decorative type.
- **Mobile is supported, not prioritised.** The desktop layout comes first. Mobile layout adapts it — it does not replace it.

---

## Coding Guidelines

### JavaScript

- Write defensive code. Every external value (localStorage, API response, URL parameter) should be validated before use.
- Avoid global side effects in functions. A function that modifies `state` and also triggers a render and also writes to localStorage is hard to test and hard to reason about. Separate concerns.
- Reuse existing helpers. Check for an existing utility before writing a new one.
- Use clear, descriptive names. A function named `getLiveRows()` is unambiguous. A function named `process()` is not.
- Minimise duplicated logic. If the same condition appears in three places, extract it.
- Keep render functions pure with respect to `state`. A render function reads `state`, produces HTML, and sets `innerHTML`. It does not modify `state`.

### Python

- Keep functions small and focused. A function that settles bets, sends Telegram messages, and updates the roadmap is doing too much.
- Make behaviour deterministic. Avoid datetime.now() inside settlement logic where the result depends on when exactly the function runs. Pass timestamps explicitly.
- Handle errors explicitly. Do not silently swallow exceptions. Log the error and either re-raise or return a structured failure result.
- Avoid hidden state. Module-level variables that accumulate across calls make behaviour unpredictable. Prefer passing state explicitly.
- Use `src/league_registry.py` for all league metadata. Do not hardcode league codes, IDs, or season models elsewhere. See ADR-004.

### CSS

- Use compact spacing. Default to tight padding and margins. Increase only when visual separation is genuinely required.
- Avoid duplicate selectors. If the same selector appears twice, consolidate it.
- Design for the laptop viewport first (~1366px width). Add responsive breakpoints as needed for smaller screens.
- Use consistent spacing units. Do not mix `px`, `rem`, and `em` for the same property across components.

---

## Validation Requirements

A task is not complete until the following have been done:

- [ ] The affected feature has been tested manually in the browser (if frontend).
- [ ] Regression check: adjacent features that could have been broken have been verified.
- [ ] Related workflows (e.g. both GitHub Actions settlement and on-demand settlement) have been validated if the change touches shared code.
- [ ] `07_Current_Status.md` updated if the project state changed.
- [ ] `05_Known_Issues.md` updated — new issues added, resolved issues removed.
- [ ] `08_Change_Log.md` updated if a phase completed.
- [ ] Any other affected documentation updated.
- [ ] Session handover created in `docs/handovers/`.

---

## Working with Claude

These guidelines apply to all development sessions conducted with Claude.

- **Read the documentation before analysing code.** `07_Current_Status.md` and `05_Known_Issues.md` describe the current development state. `09_Architecture_Decisions.md` describes constraints that must not be violated. Reading these before touching code prevents proposing solutions that have already been ruled out.
- **Respect all ADRs.** An ADR records a decision that was made with full context. Do not propose reversing one without first reading the documented reasoning and explaining why that reasoning no longer applies.
- **Check `05_Known_Issues.md` before proposing a solution.** The root cause, fix strategy, and validation checklist may already be documented. Do not re-derive a diagnosis that is already confirmed.
- **Check `07_Current_Status.md` before assuming development priorities.** The next priorities are listed there. Do not begin work on a lower-priority task when a higher-priority task is pending.
- **Explain architectural trade-offs before suggesting significant structural changes.** Any change that touches persistence, rendering architecture, or settlement routing has systemic consequences. These should be explained and discussed before implementation begins.
- **Prefer extending existing implementations over creating parallel implementations.** If `update_dataframe()` covers the need, use it. If `github_request()` covers the need, use it. A new implementation of the same concept is a liability.
- **If documentation and implementation appear to conflict, determine which is correct before making changes.** The documentation may be stale, or the implementation may have regressed. Identify the discrepancy, then update whichever is wrong.
- **Update the documentation whenever a permanent implementation change is made.** A code change without a documentation update leaves the project in an inconsistent state. The next session will start with incorrect reference material.

---

## Things to Avoid

- **Large rewrites without justification.** A rewrite discards the constraints and edge case handling embedded in the existing code. Justify a rewrite explicitly before beginning one.
- **Duplicate implementations.** If settlement logic exists in `update_dataframe()`, it is not implemented again elsewhere. Duplication diverges.
- **Duplicate persistence.** If `cloud_state.json` holds a piece of data, a second file does not also hold it. See ADR-001 and ADR-008.
- **Hardcoded production values.** API keys, rate limits, repository coordinates, and bankroll amounts belong in environment variables or `config.json`. See ADR-010.
- **Temporary fixes that become permanent.** Diagnostic instrumentation, debug print statements, and workarounds should be removed as soon as the issue they were investigating is resolved. Record the removal as part of the fix validation checklist.
- **Ignoring ADRs.** An ADR records a decision that was made deliberately. Reversing it without understanding the documented reasoning reintroduces the problem the decision solved.
- **Modifying architecture without updating documentation.** If a component is added, removed, or its role changes, `01_Architecture.md` and `04_Backend.md` (or `03_Dashboard.md`) must be updated in the same session.

---

## Implementation Philosophy

Before creating anything new, verify whether the existing implementation can be safely extended.

This applies to:

- A new helper function
- A new module or file
- A new API endpoint
- A new persistence layer or data file
- A new rendering path or page section
- A new workflow or processing pipeline

In each case, the question is: **does something that already exists cover this need?** If it does, extend it. If it genuinely does not, create the new component with a clear explanation of why extension was not possible.

Creating a new component should be the exception, not the default response to a new requirement.

**Why this matters.** Unnecessary parallel implementations increase the surface area that must be kept consistent. Two implementations of the same concept will diverge. Bugs fixed in one will not be fixed in the other. Features added to one must be remembered and added to the other. Over time, parallel implementations become the primary source of subtle, hard-to-diagnose inconsistencies — the kind where bot picks and manual bets produce different results for the same match, or where settlement behaves differently depending on which trigger initiated it.
