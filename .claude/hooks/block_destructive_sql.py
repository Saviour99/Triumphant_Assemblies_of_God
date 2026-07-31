#!/usr/bin/env python3
"""
PreToolUse guard: never allow DROP TABLE / DROP DATABASE / TRUNCATE to run
via Bash, or to be introduced into a file via Edit/Write.

Enforces the project's data-safety rule (see CLAUDE.md): this church
management system must never drop or delete a database table anywhere in
its code, migrations, or ad-hoc commands. All deletes are single-record.
"""
import json
import re
import sys

DESTRUCTIVE_PATTERN = re.compile(r'DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE', re.IGNORECASE)

REASON = (
    "Blocked: this command/content matches a destructive SQL pattern "
    "(DROP TABLE / DROP DATABASE / TRUNCATE). This project's CLAUDE.md "
    "data-safety rule forbids dropping or truncating any database table — "
    "all deletes must be single-record (soft delete preferred). If this is "
    "a false positive, stop and ask the user rather than working around it."
)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }))
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name == "Bash":
        text = tool_input.get("command", "") or ""
    elif tool_name == "Edit":
        text = tool_input.get("new_string", "") or ""
    elif tool_name == "Write":
        text = tool_input.get("content", "") or ""
    else:
        sys.exit(0)

    if DESTRUCTIVE_PATTERN.search(text):
        deny(REASON)

    sys.exit(0)


if __name__ == "__main__":
    main()
