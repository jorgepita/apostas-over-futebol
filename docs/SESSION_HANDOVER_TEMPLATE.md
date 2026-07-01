# Session Handover

> Copy this template at the end of every development session. Fill in all sections. Save as `handover-YYYY-MM-DD.md` or paste directly into the next session as the opening context.

---

## Session Information

```
Date:     YYYY-MM-DD
Branch:   main
Commit:   <short hash> — <commit message>
```

---

## Session Objective

<!-- What was the goal of this session? One or two sentences. -->

---

## Work Completed

<!-- Bullet list of everything completed. Be specific. -->

- 

---

## Files Modified

| File | Reason for change |
|---|---|
| `path/to/file.py` | <!-- why --> |

---

## Documentation Updated

<!-- List every docs/ file touched. If none, write "None." -->

- 

---

## Architectural Decisions

<!-- If any new ADRs were created or existing ones changed, record them here. -->
<!-- Otherwise write: None. -->

None.

---

## Current Project State

<!-- Choose one and add detail if needed. -->
<!-- Stable / Waiting for testing / Ready for deployment / Investigation in progress / Partial implementation -->

---

## Outstanding Issues

<!-- Reference IDs from 05_Known_Issues.md where possible. -->
<!-- Example: LIVE-1 — Live Center does not auto-refresh manual bet results (confirmed, fix not yet implemented) -->

- 

---

## Validation Performed

<!-- List every validation step completed this session. -->
<!-- Examples: manual browser test, settlement validation, API response check, localStorage inspection -->

- 

---

## Remaining Work

<!-- What still needs to be done before the current objective is fully complete? -->

- 

---

## Next Recommended Task

<!-- The single most important next task. One sentence. Specific enough for the next session to start immediately. -->

---

## Notes for the Next Session

<!-- Context that must not be forgotten. Keep concise. -->
<!-- Examples: diagnostic instrumentation is active, SHA conflict seen once, gunicorn worker count set to 1 -->

- 

---

## End-of-Session Checklist

- [ ] Code committed and pushed
- [ ] `07_Current_Status.md` updated
- [ ] `05_Known_Issues.md` updated (new issues added, resolved issues removed)
- [ ] `08_Change_Log.md` updated (if a phase completed)
- [ ] `09_Architecture_Decisions.md` updated (if a new ADR was accepted)
- [ ] `06_Roadmap.md` updated (if priorities changed)
- [ ] This handover document filled and saved
- [ ] Next session can start from "Next Recommended Task" without reading chat history

---

## How to Use This Template

1. At the end of every development session, copy this file.
2. Fill every section. Write "None." or "N/A" rather than leaving a section blank.
3. Save the filled copy as `handover-YYYY-MM-DD.md` in `/docs/handovers/` (or paste it directly into the next Claude session as the opening message).
4. The next session should read `docs/README.md` first, then this handover, before doing anything else.
