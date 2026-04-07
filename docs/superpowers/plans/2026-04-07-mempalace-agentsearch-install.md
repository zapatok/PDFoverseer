# MemPalace + AgentSearch Installation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. This is an infrastructure/tooling install — not a code feature. No TDD cycle; validation is via command output verification.

**Goal:** Install MemPalace (semantic memory MCP server) and AgentSearch (documentation browser) into the Claude Code environment.

**Architecture:** MemPalace runs as a global MCP server in an isolated Python 3.10 venv, storing vectors in ChromaDB and a knowledge graph in SQLite. AgentSearch is a zero-install npx tool integrated via CLAUDE.md instructions.

**Tech Stack:** Python 3.10, mempalace==3.0.0, ChromaDB, Node.js v24, nia-docs (npx)

**Spec:** `docs/superpowers/specs/2026-04-07-mempalace-agentsearch-design.md`

---

## Chunk 1: MemPalace — Venv & Package Install

### Task 1: Create isolated Python 3.10 venv

**Files:**
- Create: `a:\PROJECTS\.venvs\mempalace\` (venv directory)

- [ ] **Step 1: Create parent directory**

```bash
mkdir -p "a:/PROJECTS/.venvs"
```

Expected: Directory created (or already exists). No error.

- [ ] **Step 2: Create venv with Python 3.10**

```bash
"C:/Program Files/Python310/python.exe" -m venv "a:/PROJECTS/.venvs/mempalace"
```

Expected: Venv created with `Scripts/python.exe` and `Scripts/pip.exe`.

**If Python 3.10 not found at that path**, use the .venv-cuda Python as base (same 3.10.11):
```bash
"a:/PROJECTS/PDFoverseer/.venv-cuda/Scripts/python.exe" -m venv --without-pip "a:/PROJECTS/.venvs/mempalace"
# Then bootstrap pip:
"a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m ensurepip --upgrade
```

- [ ] **Step 3: Verify venv Python version**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" --version
```

Expected: `Python 3.10.x`

- [ ] **Step 4: Verify pip is available**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/pip.exe" --version
```

Expected: `pip X.Y.Z from ...mempalace...`

### Task 2: Install mempalace package

- [ ] **Step 1: Install mempalace==3.0.0**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/pip.exe" install mempalace==3.0.0
```

Expected: Successful install. Downloads chromadb, onnxruntime, pyyaml, and transitive deps. **Requires internet.** May take 2-5 minutes.

- [ ] **Step 2: Verify mempalace CLI is available**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" --version 2>&1 || "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace --version 2>&1
```

Expected: Version string (3.0.0 or similar). One of the two commands should work — mempalace may install as a console_scripts entry point or as a module.

- [ ] **Step 3: Check mempalace CLI help to understand available commands**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" --help 2>&1 || "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace --help 2>&1
```

Expected: Help output listing commands (init, mine, search, split, etc.). **Save this output** — it reveals the actual CLI interface and flags available.

- [ ] **Step 4: Verify .venv-cuda is untouched**

```bash
"a:/PROJECTS/PDFoverseer/.venv-cuda/Scripts/pip.exe" show mempalace 2>&1
```

Expected: `WARNING: Package(s) not found: mempalace` — confirms zero contamination.

- [ ] **Step 5: Commit checkpoint**

Nothing to commit to git (venv is outside the repo and should be gitignored). But note the installed version for the record:

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/pip.exe" freeze | grep -i mempalace
```

Expected: `mempalace==3.0.0`

---

## Chunk 2: MemPalace — Initialization & Configuration

### Task 3: Initialize MemPalace

- [ ] **Step 1: Check mempalace init help for flags**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" init --help 2>&1 || "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace init --help 2>&1
```

Expected: Help output showing whether init takes `--palace`, `--identity`, `--non-interactive` or similar flags. **Read carefully** — determines whether the next steps are interactive or scriptable.

- [ ] **Step 2: Run mempalace init**

If init is interactive, provide these values when prompted:
- **Palace path:** `C:\Users\Daniel\.mempalace` (default, global)
- **Identity:** `Daniel — software engineer building PDFoverseer, a PDF document analyzer with OCR + AI inference`

If init supports flags:
```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" init "C:/Users/Daniel/.mempalace"
```

Expected: Palace directory created at `C:\Users\Daniel\.mempalace\` with config files.

- [ ] **Step 3: Verify palace directory was created**

```bash
ls "C:/Users/Daniel/.mempalace/" 2>&1
```

Expected: Shows config.json, possibly wing_config.json, identity.txt, and/or data directories.

- [ ] **Step 4: Configure wing for PDFoverseer**

Check if wing_config.json exists and add the pdfoverseer wing. If mempalace has a CLI command for this:
```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" wing add pdfoverseer --help 2>&1
```

If manual config is needed, edit `C:\Users\Daniel\.mempalace\wing_config.json`:
```json
{
  "pdfoverseer": {
    "keywords": ["PDFoverseer", "OCR", "inference", "Tesseract", "pipeline"],
    "description": "PDF document analyzer — OCR + AI inference engine"
  }
}
```

- [ ] **Step 5: Set identity if not done during init**

Write to `C:\Users\Daniel\.mempalace\identity.txt`:
```
Daniel — software engineer building PDFoverseer, a PDF document analyzer with OCR + AI inference
```

### Task 4: Check mining exclusion support

- [ ] **Step 1: Check mine command help**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" mine --help 2>&1 || "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace mine --help 2>&1
```

Expected: Help output showing flags for exclusion patterns (`--exclude`, `--ignore`, `--skip`, or similar). **Save this output.**

- [ ] **Step 2: Document exclusion strategy**

Based on mine help output, determine the command to mine PDFoverseer while excluding:
- `data/` (PNGs, JSON data files, inspection images)
- `models/` (FSRCNN/EDSR .pb files)
- `frontend/node_modules/`
- `.venv-cuda/`
- `archived/`
- `eval/*/results/` (sweep result JSONs)

If no exclude flags exist, check if mempalace respects `.gitignore` or has its own ignore file.

**Decision point:** If mempalace cannot exclude directories, consider mining only specific subdirectories (core/, api/, vlm/, eval/, tools/, docs/) instead of the project root.

---

## Chunk 3: MemPalace — MCP Registration & Episodic-Memory Swap

### Task 5: Register MCP server globally

- [ ] **Step 1: Register mempalace MCP server**

```bash
claude mcp add -s user mempalace -- "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace.mcp_server
```

Expected: Confirmation message that the MCP server was added.

**If the command fails** (e.g., module path wrong), try alternative module paths:
```bash
# Try these if the first fails:
claude mcp add -s user mempalace -- "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace.server
claude mcp add -s user mempalace -- "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace.mcp
```

- [ ] **Step 2: Verify MCP server appears in global settings**

```bash
claude mcp list 2>&1
```

Expected: Shows `mempalace` in the list with status information.

- [ ] **Step 3: Test MCP server starts successfully**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace.mcp_server 2>&1 &
sleep 3
# If it started, kill it
kill %1 2>/dev/null
```

Expected: Server starts without import errors or crashes. May print connection info or wait for stdin (MCP servers communicate via stdio). A clean start with no tracebacks is success.

### Task 6: Deactivate episodic-memory for PDFoverseer

**Files:**
- Modify: `a:\PROJECTS\PDFoverseer\.claude\settings.local.json`

- [ ] **Step 1: Deactivate episodic-memory plugin**

In `a:\PROJECTS\PDFoverseer\.claude\settings.local.json`, change:
```json
"episodic-memory@superpowers-marketplace": true
```
to:
```json
"episodic-memory@superpowers-marketplace": false
```

This disables the plugin for PDFoverseer only. Global settings do not list it, so this is sufficient.

- [ ] **Step 2: Commit configuration change**

```bash
cd "a:/PROJECTS/PDFoverseer"
git add .claude/settings.local.json
git commit -m "chore: deactivate episodic-memory, prepare for mempalace MCP"
```

### Task 7: Validation checkpoint — new session

**This step requires starting a NEW Claude Code session.**

- [ ] **Step 1: Close current Claude Code session**

The user must close the current session and start a new one for MCP changes to take effect.

- [ ] **Step 2: In new session, verify mempalace tools appear**

Ask the assistant: "What mempalace tools do you have available?"

Expected: The assistant should list mempalace-related MCP tools (search, status, navigation, etc.).

- [ ] **Step 3: Verify episodic-memory tools are gone**

Ask: "Do you have any episodic-memory tools?"

Expected: No episodic-memory tools available. If they persist, also run:
```bash
claude mcp remove episodic-memory
```

- [ ] **Step 4: Verify other plugins still work**

Quick check: superpowers skills, hookify rules, feature-dev — all should be unaffected.

---

## Chunk 4: MemPalace — Mining & Functional Tests

### Task 8: Mine PDFoverseer codebase

- [ ] **Step 1: Run mine with exclusions**

Use the command determined in Task 4, Step 2. Example (adjust flags based on actual CLI):

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" mine "a:/PROJECTS/PDFoverseer" --wing pdfoverseer
```

Expected: Mining starts, processes Python files, markdown docs, etc. **First run downloads the embedding model (~100MB, needs internet).** May take 2-10 minutes depending on codebase size and exclusions.

- [ ] **Step 2: Verify mining completed**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" search "inference engine" --wing pdfoverseer 2>&1
```

Expected: Returns results related to inference engine code/docs from PDFoverseer.

- [ ] **Step 3: Test semantic search quality**

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" search "INS_31 last page bug" --wing pdfoverseer 2>&1
```

Expected: Returns results mentioning INS_31, phase 5b, ph5b_ratio_min, or related content.

```bash
"a:/PROJECTS/.venvs/mempalace/Scripts/mempalace.exe" search "OCR digit normalization" --wing pdfoverseer 2>&1
```

Expected: Returns results from core/utils.py or docs mentioning O→0, I→1 mappings.

### Task 9: Test hooks on Windows

- [ ] **Step 1: Locate hook files**

```bash
find "C:/Users/Daniel/.mempalace" -name "*.sh" 2>/dev/null
ls "C:/Users/Daniel/.mempalace/hooks/" 2>/dev/null
```

Expected: Finds .sh hook files (if mempalace installed any during init).

- [ ] **Step 2: Test bash resolution**

```bash
which bash 2>&1
bash --version 2>&1 | head -1
```

Expected: Points to `C:\Program Files\Git\usr\bin\bash.exe` (Git Bash), not WSL.

- [ ] **Step 3: Test hook execution (if hooks exist)**

```bash
bash "C:/Users/Daniel/.mempalace/hooks/<hook-name>.sh" 2>&1
```

Expected: Executes without "command not found" or WSL-related errors.

**If no hooks found:** Skip this task — mempalace may not use file-system hooks in v3.0.0, or hooks may be configured separately. Document finding.

---

## Chunk 5: AgentSearch — Setup & Integration

### Task 10: Test AgentSearch manually

- [ ] **Step 1: Test npx nia-docs with a known URL**

```bash
npx nia-docs https://fastapi.tiangolo.com -c "tree -L 1" 2>&1
```

Expected: Downloads package on first run (~30-60s), then shows directory tree of FastAPI docs. Output should list markdown files.

**If this fails:** Check npx cache, try `npx --yes nia-docs ...`, or verify npm registry access.

- [ ] **Step 2: Test reading a specific page**

```bash
npx nia-docs https://fastapi.tiangolo.com -c "cat tutorial/first-steps.md" 2>&1 | head -50
```

Expected: Shows markdown content of FastAPI's first-steps tutorial page.

- [ ] **Step 3: Test search within docs**

```bash
npx nia-docs https://fastapi.tiangolo.com -c "grep -rl 'WebSocket' ." 2>&1
```

Expected: Lists files containing "WebSocket".

### Task 11: Add AgentSearch instructions to CLAUDE.md

**Files:**
- Modify: `a:\PROJECTS\PDFoverseer\CLAUDE.md`

- [ ] **Step 1: Append Documentation Access section to CLAUDE.md**

Add the following block at the end of CLAUDE.md (before any closing markers if present):

```markdown
## Documentation Access (AgentSearch)

When you need current documentation for any library used in this project, use `npx nia-docs` to query it directly:

```bash
# Browse structure
npx nia-docs <docs-url> -c "tree -L 1"

# Read a page
npx nia-docs <docs-url> -c "cat <page>.md"

# Search across docs
npx nia-docs <docs-url> -c "grep -rl '<term>' ."
```

Commonly used documentation URLs:
- PyMuPDF: https://pymupdf.readthedocs.io
- FastAPI: https://fastapi.tiangolo.com
- Tesseract: https://tesseract-ocr.github.io/tessdoc/
- React: https://react.dev
- Vite: https://vite.dev/guide/
- ChromaDB: https://docs.trychroma.com

Use this BEFORE implementing anything that depends on external API behavior, especially if your training data may be outdated.
```

- [ ] **Step 2: Commit CLAUDE.md change**

```bash
cd "a:/PROJECTS/PDFoverseer"
git add CLAUDE.md
git commit -m "docs: add AgentSearch (nia-docs) instructions to CLAUDE.md"
```

---

## Chunk 6: Cross-Validation

### Task 12: Full integration validation

**This requires a NEW Claude Code session to pick up all changes.**

- [ ] **Step 1: Start new session and test mempalace context recall**

Ask the assistant: "What do you know about PDFoverseer's inference engine without reading any files?"

Expected: The assistant uses mempalace tools to search and returns relevant context about the 5-phase inference engine, Dempster-Shafer validation, etc. — WITHOUT having to Read files.

- [ ] **Step 2: Test agentsearch from session**

Ask the assistant to look up current PyMuPDF documentation for a specific API.

Expected: The assistant runs `npx nia-docs https://pymupdf.readthedocs.io -c "..."` and returns current documentation.

- [ ] **Step 3: Verify auto-memory still works**

The assistant should still be able to read MEMORY.md and access the 39 .md files for user preferences/feedback.

- [ ] **Step 4: Verify other plugins are unaffected**

Test a superpowers skill (e.g., brainstorming), verify hookify rules fire, check feature-dev works.

- [ ] **Step 5: Verify .venv-cuda isolation**

```bash
"a:/PROJECTS/PDFoverseer/.venv-cuda/Scripts/pip.exe" list 2>&1 | grep -i "mempalace\|chromadb\|onnxruntime\|sentence.transformers"
```

Expected: No mempalace, chromadb, onnxruntime, or sentence-transformers packages. Any existing packages (e.g., onnxruntime if already present for CUDA work) should match pre-install state — no NEW packages added.

- [ ] **Step 6: Final commit — update spec status**

In `docs/superpowers/specs/2026-04-07-mempalace-agentsearch-design.md`, change:
```
**Status:** Draft (rev 2 — post deep review)
```
to:
```
**Status:** Complete — installed and validated
```

```bash
cd "a:/PROJECTS/PDFoverseer"
git add docs/superpowers/specs/2026-04-07-mempalace-agentsearch-design.md
git commit -m "docs(spec): mark mempalace + agentsearch as installed and validated"
```
