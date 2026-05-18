# ADR-014: Progress Reporting

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Support a simple spoken and printed progress summary for children, parents, and teachers. Available on demand at any time, not just at session end.

### Rationale

Progress visibility matters for three audiences with different needs:

- **The child** needs immediate positive reinforcement — hearing "You know 12 keys now, and your best speed today was 8 words per minute" is motivating and concrete.
- **The parent** needs to know the child is progressing and the tool is working, without needing to interpret raw data.
- **The teacher** needs enough detail to report to a school or make curriculum decisions.

All three are served by the same summary at different verbosity levels. The summary is generated from the SQLite data already being collected — no additional data capture is needed.

### Summary Levels

**Child summary** (spoken, brief, celebratory):
- Keys mastered
- Current layer active (drills only / drills + real words)
- Milestone level reached
- Vocabulary coverage percentage ("you can now type X% of everyday words") — reported as a live motivating signal between milestones
- Clean words today (words typed correctly on first attempt — a concrete accuracy signal meaningful to a child)
- Best execution speed today (reported only at Diamond milestone and above)
- Streak (days practiced in a row)

**Parent/teacher summary** (spoken + printable text file):
- Everything in child summary
- Per-key accuracy breakdown
- Session history (date, duration, keys practiced)
- Milestone dates
- Words per minute trend over time

The printable summary is a plain `.txt` file written to the desktop (or a configured folder), readable by any screen reader. No PDF, no formatting complexity, no dependencies.

### Alternatives Considered

- **Raw SQLite access only:** Rejected for v1. Teachers cannot reasonably be expected to query a database.
- **Web dashboard:** Rejected. Adds server complexity, breaks offline-first principle.
- **PDF report:** Rejected. Adds a dependency (PDF library) for no benefit over plain text for screen reader users.
