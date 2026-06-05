#!/bin/bash
# PreToolUse(Write|Edit) wrapper → delegates to the Python guard, which handles
# Windows paths + JSON cleanly. The hook event JSON on stdin flows through to Python.
# -X utf8 forces UTF-8 stdout so the accented Spanish reason text never crashes.
python -X utf8 "$(dirname "$0")/guard-editable-deliverables.py"
