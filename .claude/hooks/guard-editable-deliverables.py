#!/usr/bin/env python3
"""PreToolUse(Write|Edit) guard: protect hand-editable deliverables from blind overwrite.

When Claude is about to Write/Edit an existing ``.xlsx`` / ``.docx`` / ``.pptx`` /
``.pdf``, this hook:

1. makes a dated backup next to the file (so hand-edited work is never lost), and
2. returns ``permissionDecision="ask"`` so the user confirms the overwrite.

New files (no existing target) pass through silently — the risk is *overwriting*
work, not creating something new. Rationale: a ``.docx`` Daniel had hand-edited for
~4 h was once regenerated without warning and lost, with no backup. Even if the
"ask" path ever failed, the backup made here makes that loss impossible to repeat.

Written in Python (not bash) so Windows paths with backslashes are handled natively
by ``os.path`` / ``shutil`` instead of breaking Git Bash ``cp`` / ``test -f``.
"""

import datetime
import json
import os
import shutil
import sys

try:  # Windows stdout defaults to cp1252; the reason text carries accents + «».
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

DELIVERABLE_EXTS = (".xlsx", ".docx", ".pptx", ".pdf")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # unparseable input → never interfere

    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path or not file_path.lower().endswith(DELIVERABLE_EXTS):
        sys.exit(0)

    path = os.path.normpath(file_path)
    if not os.path.isfile(path):
        sys.exit(0)  # creating a new file → no overwrite risk

    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup = f"{path}.bak-{stamp}"
    try:
        shutil.copy2(path, backup)
        backup_note = f"Backup creado: {os.path.basename(backup)}. "
    except OSError as exc:
        backup_note = f"(No se pudo crear backup: {exc}) "

    name = os.path.basename(path)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"«{name}» es un entregable editable a mano y ya existe; "
                f"sobrescribirlo puede pisar trabajo manual. {backup_note}"
                "Confirma antes de regenerarlo."
            ),
            "additionalContext": (
                "User-editable deliverable overwrite. Per project convention, do not "
                "regenerate hand-editable files (.xlsx/.docx/.pptx/.pdf) without explicit "
                "user approval; a dated backup was just created next to the file."
            ),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
