#!/bin/bash
# Stop hook wrapper → delegates to the Python push reminder. stdin flows through.
# -X utf8 forces UTF-8 stdout so the accented message never crashes on Windows.
python -X utf8 "$(dirname "$0")/remind-push.py"
