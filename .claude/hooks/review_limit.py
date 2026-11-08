"""One /code-review per developer message: a second is blocked until the developer writes again.

Run by the hooks in .claude/settings.json with one argument, the event:
  prompt  UserPromptSubmit: the developer wrote, so a review is allowed again.
  pre     PreToolUse on Skill: allow the first code-review, deny any later one.
  post    PostToolUse on Skill: after a code-review, tell Claude to stop and report.
"""

import json
import sys
import tempfile
from pathlib import Path

STOP_AND_REPORT = (
    "This was the one code review allowed for this message from the developer. "
    "Do not run another. Fix what the findings and the developer's instructions call for, "
    "then end your turn with: what this review found and what you fixed, what you left and why, "
    "and what another review pass would most likely bring (new defects, or only rewording) "
    "and whether you think it is worth its cost. The developer decides whether to run it."
)

BLOCKED = (
    "Blocked by the project's review limit: one /code-review per developer message, "
    "and one has already run. Do not retry or work around this. Stop, and end your turn "
    "with a summary of what another pass would bring, so the developer can decide."
)


def marker(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return Path(tempfile.gettempdir()) / f"takki-code-review-{safe}"


def is_code_review(payload: dict) -> bool:
    skill = str(payload.get("tool_input", {}).get("skill", ""))
    return skill == "code-review" or skill.endswith(":code-review")


def main() -> None:
    event = sys.argv[1]
    payload = json.load(sys.stdin)
    flag = marker(str(payload.get("session_id", "")))

    if event == "prompt":
        flag.unlink(missing_ok=True)
        return

    if not is_code_review(payload):
        return

    if event == "pre":
        if flag.exists():
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": BLOCKED,
                        }
                    }
                )
            )
            return
        flag.touch()
        return

    if event == "post":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": STOP_AND_REPORT,
                    }
                }
            )
        )


if __name__ == "__main__":
    main()
