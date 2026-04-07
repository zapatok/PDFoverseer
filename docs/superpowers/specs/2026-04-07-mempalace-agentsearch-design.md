# MemPalace + AgentSearch Integration Design

**Date:** 2026-04-07
**Status:** Draft
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

#### Installation Layout

```
a:\PROJECTS\.venvs\mempalace\          # Isolated Python venv
    Scripts\python.exe                  # Used by MCP server command
    Lib\site-packages\                  # chromadb, sentence-transformers, mempalace

C:\Users\Daniel\.mempalace\            # Palace data (global)
    config.json                         # palace_path, collection_name
    wing_config.json                    # Wing: pdfoverseer (+ future projects)
    identity.txt                        # Layer 0 identity (~1 line)
    chroma_data\                        # Vector DB + SQLite KG
```

#### Dependencies

| Package | Purpose | Impact |
|---------|---------|--------|
| `chromadb>=0.4.0,<1` | Vector database for semantic search | ~200-500MB RAM when active |
| `sentence-transformers` (via chromadb) | `all-MiniLM-L6-v2` embedding model | ~100MB download (one-time) |
| `pyyaml>=6.0` | Config parsing | Negligible |
| SQLite (stdlib) | Knowledge graph | Zero additional impact |

All dependencies install into the isolated venv. Zero impact on `.venv-cuda` or system Python.

**Resource estimate:** MemPalace MCP server uses ~500MB RAM at peak (ChromaDB + embeddings). Combined with CUDA venv (~2-4GB), Tesseract workers (~1GB), and React dev server (~200MB), total is well under 10GB — comfortable on 32GB. Disk: ~500MB for venv + model, ~100-300MB for mined data.

#### MCP Server Registration

Registered globally in `C:\Users\Daniel\.claude\settings.json`:

```bash
claude mcp add mempalace -- "a:\PROJECTS\.venvs\mempalace\Scripts\python.exe" -m mempalace.mcp_server
```

Exposes 19 tools (search, navigation, KG queries, agent diary). Claude Code starts/stops the server process per session automatically.

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

**Mining exclusions:** The mine command should skip binary/irrelevant directories to avoid polluting search results. Verify whether mempalace auto-excludes common patterns (node_modules, .venv, .git, *.png, *.pb). If not, exclude manually: `data/`, `models/`, `frontend/node_modules/`, `.venv-cuda/`, `archived/`, `eval/*/results/`.

**Not mined initially:**
- Auto-memory files (39 .md) — deferred to manual review with user
- Claude Code conversation exports — requires format verification first

#### Hooks (Windows Consideration)

MemPalace auto-save hooks are `.sh` files. On Windows, these run via Git Bash (already installed). No adaptation to `.ps1`/`.bat` needed.

#### Episodic-Memory Handling

- **Deactivated** in PDFoverseer's `.claude/settings.local.json` (removed from `enabledPlugins`)
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

#### Requirements

- Node.js >= 18 (verify during installation)
- No persistent install — `npx` handles download/cache
- Cross-platform (uses `just-bash` embedded bash shell on Windows)

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

1. Create isolated venv at `a:\PROJECTS\.venvs\mempalace\`
2. `pip install mempalace` in that venv (pin to latest stable at install time for reproducibility)
3. `mempalace init` — configure identity, wing `pdfoverseer`
4. Register MCP server globally via `claude mcp add`
5. Deactivate episodic-memory in PDFoverseer settings
6. Validate: new session, verify 19 mempalace tools appear
7. Mine PDFoverseer codebase: `mempalace mine a:\PROJECTS\PDFoverseer --wing pdfoverseer`
8. Functional test: search for known concepts ("inference engine", "INS_31 bug")
8b. Hook test: trigger an auto-save hook, verify it executes via Git Bash on Windows

### Phase 2: AgentSearch Setup

9. Verify Node.js >= 18 installed
10. Manual test: `npx nia-docs https://fastapi.tiangolo.com -c "tree -L 1"`
11. Append instruction block to CLAUDE.md
12. Functional test: query docs for a project library

### Phase 3: Cross-Validation

13. New session: verify mempalace recalls project context
14. Verify agentsearch works from CLAUDE.md instructions
15. Verify auto-memory still functions (feedback/preferences)
16. Verify other plugins unaffected (superpowers, hookify, feature-dev, etc.)

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

1. **MemPalace Windows hooks:** `.sh` hooks require Git Bash — should work but untested on this system
2. **MemPalace open issues:** Shell injection in hooks (#110), ChromaDB pinning (#100) — non-blocking for local use
3. **AgentSearch maturity:** v0.2.3, private source repo, some commands slow on large doc sites (>60s)
4. **Conversation mining:** Claude Code conversation export format needs verification before mining — deferred to post-install
