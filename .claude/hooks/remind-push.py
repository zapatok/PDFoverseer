#!/usr/bin/env python3
"""Stop hook: non-blocking reminder to push when the branch is ahead of its remote.

Compares the current branch against its configured upstream, or ``origin/<branch>``
when no upstream is set (``po_overhaul`` has no upstream configured, but
``origin/po_overhaul`` exists as a remote-tracking ref). Surfaces a ``systemMessage``
only — it never sets ``decision: "block"``, so the turn always completes and there is
zero risk of a Stop-hook loop.
"""

import json
import subprocess
import sys

try:  # Windows stdout defaults to cp1252; the message carries accents + 📤.
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def git(*args: str) -> str:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def main() -> None:
    try:
        json.load(sys.stdin)  # consume the event payload (unused)
    except (json.JSONDecodeError, ValueError):
        pass

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":  # detached HEAD or not a git repo
        sys.exit(0)

    ref = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if not ref and git("rev-parse", "--verify", "--quiet", f"origin/{branch}"):
        ref = f"origin/{branch}"
    if not ref:
        sys.exit(0)  # no remote counterpart → nothing to push to

    count = git("rev-list", "--count", f"{ref}..HEAD")
    try:
        ahead = int(count)
    except ValueError:
        sys.exit(0)
    if ahead <= 0:
        sys.exit(0)

    plural = "s" if ahead != 1 else ""
    message = (
        f"📤 {ahead} commit{plural} sin pushear en «{branch}» (vs {ref}). "
        "Convención del proyecto: pushear al cierre de cada ronda."
    )
    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


if __name__ == "__main__":
    main()
