# MemPalace + AgentSearch Integration Design

**Date:** 2026-04-07
**Status:** Draft (rev 2 — post deep review)
**Approach:** B (sequential — mempalace first, agentsearch second)

## Problem Statement

Every new Claude Code session starts from zero. The current memory systems (auto-memory: 39 flat .md files with a plain index; episodic-memory: MCP plugin) do not provide useful contextual recall. The assistant must re-read the codebase and rediscover project context each session, wasting time and tokens.

Additionally, the assistant has no access to current external documentation, risking implementation of deprecated APIs or outdated patterns.

## Goals

1. **Persistent semantic memory** across Claude Code sessions — decisions, architecture, conversation history retrievable by meaning, not just filename
2. **Current documentation access** — query up-to-date docs for any library from within a session
3. **Zero interference** with existing project code, `.venv-cuda`, or other plugins
4. **Reversible** — full rollback path if either tool causes issues

## Non-Goals

- Migrating existing auto-memory files (deferred to manual review)
- Replacing auto-memory entirely (it stays active for user preferences/feedback)
- Modifying PDFoverseer source code
- Uninstalling episodic-memory (only deactivated per-project)

## Design

### Component 1: MemPalace (Semantic Memory)

**What:** Open-source, locally-hosted AI memory system using ChromaDB (vector search) + SQLite (knowledge graph). Stores verbatim conversations and code, searchable by semantic meaning. Organizes via "palace" metaphor: wings (projects), rooms (topics).

**Repository:** https://github.com/milla-jovovich/mempalace
**PyPI:** `mempalace` v3.0.0 (verified on PyPI, latest stable as of 2026-04-07)

#### Installation Layout

```
a:\PROJECTS\.venvs\                    # Parent dir (must be created: mkdir)
└── mempalace\                         # Isolated Python 3.10 venv
    Scripts\python.exe                 # Used by MCP server command
    Lib\site-packages\                 # chromadb, sentence-transformers, mempalace

C:\Users\Daniel\.mempalace\            # Palace data (global)
    config.json                         # palace_path, collection_name
    wing_config.json                    # Wing: pdfoverseer (+ future projects)
    identity.txt                        # Layer 0 identity (~1 line)
    chroma_data\                        # Vector DB + SQLite KG
```

#### Dependencies

| Package | Purpose | Impact |
|---------|---------|--------|
| `chromadb==1.5.6` | Vector database for semantic search (embedded, no separate server) | ~200-500MB RAM when active |
| `onnxruntime` (via chromadb) | Embedding model runtime (`all-MiniLM-L6-v2`) | ~100MB download (one-time, needs internet) |
| `pyyaml>=6.0` | Config parsing | Negligible |
| SQLite (stdlib) | Knowledge graph | Zero additional impact |
| `kubernetes`, `grpcio`, `opentelemetry-*` | ChromaDB transitive deps | Installed but not actively used in embedded mode |

All dependencies install into the isolated venv. Zero impact on `.venv-cuda` or system Python.

**Python version:** The venv MUST be created with Python 3.10 (not system Python 3.14.3). ChromaDB and onnxruntime may not have wheels for 3.14. Use the base Python 3.10 interpreter to create the venv:
```bash
"C:/Python310/python.exe" -m venv "a:/PROJECTS/.venvs/mempalace"
```
If no standalone 3.10 is available outside `.venv-cuda`, use the venv's Python directly:
```bash
"a:/PROJECTS/PDFoverseer/.venv-cuda/Scripts/python.exe" -m venv --without-pip "a:/PROJECTS/.venvs/mempalace"
```
Then bootstrap pip manually with `get-pip.py`.

**Resource estimate:** MemPalace MCP server uses ~500MB RAM at peak (ChromaDB runs embedded in-process, no separate server). Combined with CUDA venv (~2-4GB), Tesseract workers (~1GB), and React dev server (~200MB), total is well under 10GB — comfortable on 32GB. Disk: ~500MB for venv + model, ~100-300MB for mined data.

**Network:** First `pip install` and first `mempalace mine` (embedding model download) require internet. After that, fully offline.

#### MCP Server Registration

Registered globally in `C:\Users\Daniel\.claude\settings.json`:

```bash
claude mcp add -s user mempalace -- "a:/PROJECTS/.venvs/mempalace/Scripts/python.exe" -m mempalace.mcp_server
```

**Note:** `-s user` registers globally (in `~/.claude/settings.json`). Without it, default scope is `local` (project-only). Forward slashes used to avoid bash escape issues on Windows.

Exposes tools (search, navigation, KG queries, agent diary). Claude Code starts/stops the server process per session automatically. If the MCP server crashes mid-session, tools become unavailable until the next session (Claude Code does not auto-restart crashed MCP servers).

#### Wing Configuration

```json
{
  "pdfoverseer": {
    "keywords": ["PDFoverseer", "OCR", "inference", "Tesseract", "pipeline"],
    "description": "PDF document analyzer — OCR + AI inference engine"
  }
}
```

Future projects get their own wings. Searches can be scoped: `--wing pdfoverseer --room inference`.

#### Initial Mining

| Source | Command | Wing |
|--------|---------|------|
| PDFoverseer code | `mempalace mine a:\PROJECTS\PDFoverseer --wing pdfoverseer` | pdfoverseer |

**Mining exclusions:** The mine command should skip binary/irrelevant directories to avoid polluting search results. Verify whether mempalace auto-excludes common patterns (node_modules, .venv, .git, *.png, *.pb). If not, exclude manually: `data/`, `models/`, `frontend/node_modules/`, `.venv-cuda/`, `archived/`, `eval/*/results/`, `data/inspection/`, `data/ocr_all/`, `data/ocr_failures/`.

**Re-mining strategy:** `mempalace mine` should be re-run after significant code changes (new modules, major refactors, branch merges). Frequency: manual, not automated. Determine during install whether mine is incremental or full re-index.

**Not mined initially:**
- Auto-memory files (39 .md) — deferred to manual review with user
- Claude Code conversation exports — requires format verification first

#### Hooks (Windows Consideration)

MemPalace auto-save hooks are `.sh` files. Three `bash.exe` binaries exist on this system:
1. `C:\Program Files\Git\usr\bin\bash.exe` (Git Bash) — **first in PATH**
2. `C:\Windows\System32\bash.exe` (WSL)
3. `C:\Users\Daniel\AppData\Local\Microsoft\WindowsApps\bash.exe` (WSL alias)

Git Bash is first in PATH, so `subprocess.run(["bash", ...])` should resolve correctly. However, this must be verified during install (step 8b). If mempalace hardcodes a different bash path or uses `sh` instead of `bash`, the hooks may fail. Fallback: set `BASH_PATH` env var or adapt hooks to `.ps1` if needed.

#### Episodic-Memory Handling

- **Deactivated** in PDFoverseer's `.claude/settings.local.json` by setting `"episodic-memory@superpowers-marketplace": false` (or removing the key). Global settings do NOT list episodic-memory, so project-level deactivation is sufficient.
- Verify after deactivation that episodic-memory MCP tools no longer appear in session. If they persist, also run `claude mcp remove` for the plugin's MCP entry.
- **Not uninstalled** globally — available for reactivation if needed
- **Data preserved** — episodic-memory's stored conversations remain intact

### Component 2: AgentSearch (Documentation Access)

**What:** CLI tool that crawls documentation websites, converts to local markdown, and provides bash-like navigation (`tree`, `cat`, `grep`). Zero install via `npx`.

**Package:** `nia-docs` v0.2.3 (npm, MIT license)
**Website:** https://www.agentsearch.sh/

#### Integration Method

Append instruction block to `CLAUDE.md` (project-level, not global — relevant docs vary per project). No MCP server, no venv, no config files.

The block teaches the assistant how to invoke `npx nia-docs <url> -c "<command>"` when it needs current documentation.

#### Usage Examples

```bash
# Browse docs structure
npx nia-docs https://pymupdf.readthedocs.io -c "tree -L 1"

# Read specific page
npx nia-docs https://pymupdf.readthedocs.io -c "cat pixmap.md"

# Search across docs
npx nia-docs https://fastapi.tiangolo.com -c "grep -rl 'WebSocket' ."
```

#### CLAUDE.md Instruction Block

The following block is appended to `CLAUDE.md` under a new `## Documentation Access` section:

```markdown
## Documentation Access (AgentSearch)

When you need current documentation for any library used in this project, use `npx nia-docs` to query it directly:

\`\`\`bash
# Browse structure
npx nia-docs <docs-url> -c "tree -L 1"

# Read a page
npx nia-docs <docs-url> -c "cat <page>.md"

# Search across docs
npx nia-docs <docs-url> -c "grep -rl '<term>' ."
\`\`\`

Commonly used documentation URLs:
- PyMuPDF: https://pymupdf.readthedocs.io
- FastAPI: https://fastapi.tiangolo.com
- Tesseract: https://tesseract-ocr.github.io/tessdoc/
- React: https://react.dev
- Vite: https://vite.dev/guide/
- ChromaDB: https://docs.trychroma.com

Use this BEFORE implementing anything that depends on external API behavior, especially if your training data may be outdated.
```

#### Requirements

- Node.js >= 18 (verified: v24.14.0 on this system)
- No persistent install — `npx` handles download/cache
- Cross-platform (uses `just-bash` embedded bash shell on Windows)
- **First invocation per URL is slow** (~30-60s) due to npx cold-start + page crawling. Subsequent runs use cache.

#### Relevant Documentation URLs for PDFoverseer

| Library | Docs URL |
|---------|----------|
| PyMuPDF | `https://pymupdf.readthedocs.io` |
| FastAPI | `https://fastapi.tiangolo.com` |
| Tesseract | `https://tesseract-ocr.github.io/tessdoc/` |
| React | `https://react.dev` |
| Vite | `https://vite.dev/guide/` |
| ChromaDB | `https://docs.trychroma.com` |

## Execution Order

### Phase 1: MemPalace Installation

1. Create parent dir: `mkdir -p "a:/PROJECTS/.venvs"`
2. Create isolated Python 3.10 venv (see Python version section above for exact command)
3. Activate venv, `pip install mempalace==3.0.0` (pinned)
4. Run `mempalace init` — determine if interactive; provide identity + wing `pdfoverseer` config
5. Verify mining exclusion support: check `mempalace mine --help` for exclude flags
6. Register MCP server globally: `claude mcp add -s user mempalace -- ...` (see command above)
7. Deactivate episodic-memory in PDFoverseer's `.claude/settings.local.json`
8. **Validation checkpoint:** Start new Claude Code session, verify mempalace tools appear
9. Mine PDFoverseer codebase: `mempalace mine a:\PROJECTS\PDFoverseer --wing pdfoverseer` (with appropriate exclusions)
10. Functional test: search for known concepts ("inference engine", "INS_31 bug")
11. Hook test: trigger an auto-save hook, verify it executes correctly on Windows (bash resolution check)

### Phase 2: AgentSearch Setup

12. Node.js already verified: v24.14.0
13. Manual test: `npx nia-docs https://fastapi.tiangolo.com -c "tree -L 1"` (expect ~30-60s first run)
14. Append instruction block to CLAUDE.md (exact content defined above)
15. Functional test: assistant queries docs for a project library from within session

### Phase 3: Cross-Validation

16. New session: verify mempalace recalls project context without re-reading files
17. Verify agentsearch responds to doc queries triggered by CLAUDE.md instructions
18. Verify auto-memory still functions (feedback/preferences files readable)
19. Verify other plugins unaffected (superpowers, hookify, feature-dev, etc.)
20. Verify `.venv-cuda` is untouched: `pip list` in .venv-cuda should show no new packages

## Rollback Plan

| Problem | Action |
|---------|--------|
| MemPalace MCP won't start | `claude mcp remove mempalace`, reactivate episodic-memory |
| ChromaDB crashes or conflicts | Delete and recreate venv (isolated, zero risk to project) |
| MemPalace tools not appearing | Check MCP server logs, verify Python path in registration |
| AgentSearch fails or too slow | Remove instruction block from CLAUDE.md (one edit) |
| Other plugins break | Compare settings.json before/after, revert changes |

## What This Plan Does NOT Touch

- `.venv-cuda` (project's CUDA Python environment)
- PDFoverseer source code (core/, api/, vlm/, frontend/, etc.)
- Auto-memory files (39 .md files — reviewed separately later)
- Episodic-memory installation (only deactivated, not removed)
- Global plugin configuration (only MCP server added)

## Known Risks

1. **MemPalace Windows hooks:** `.sh` hooks depend on bash PATH resolution — Git Bash is first but WSL bash also present. Tested in step 11.
2. **MemPalace open issues:** Shell injection in hooks (#110), ChromaDB pinning (#100) — non-blocking for local use
3. **AgentSearch maturity:** v0.2.3, private source repo (GitHub 404), some commands slow on large doc sites (>60s). If package disappears from npm, only impact is losing doc access — no data loss. Fallback: use `WebFetch` tool directly.
4. **Conversation mining:** Claude Code conversation export format needs verification before mining — deferred to post-install
5. **Python 3.10 venv creation:** If standalone Python 3.10 is not available outside `.venv-cuda`, creating the venv requires `--without-pip` + manual pip bootstrap. Tested in step 2.
6. **MCP server crash:** If mempalace MCP crashes mid-session, tools become unavailable until next session. No auto-restart. Low probability, acceptable risk.
