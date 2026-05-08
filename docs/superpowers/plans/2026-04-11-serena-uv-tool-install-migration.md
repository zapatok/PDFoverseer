# Serena Migration: uvx → uv tool install + Full Hook Suite

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Serena MCP from `uvx --from git+…` (ephemeral per-invocation) to `uv tool install` (locally installed binary), cutting startup cold-start from ~0.93s to ~0.05s and unlocking the full `serena-hooks` suite (`activate` + `cleanup` + `remind` + `auto-approve`).

**Architecture:** Two sequential phases with a user-driven restart checkpoint between them. Phase 1 replaces the existing uvx-based install in `~/.claude.json` (MCP entry) and `~/.claude/settings.json` (existing `activate` hook) with direct `serena` / `serena-hooks` binary invocations — this is the *functional equivalent* of the current setup but faster. Phase 2 adds the three remaining hooks (`cleanup`, `remind`, `auto-approve`) that are only viable after Phase 1. Both phases touch only user-scope config (`~/.claude*`); the PDFoverseer repo is NOT modified. Rollback is `uv tool uninstall serena` + reverting two JSON files.

**Tech stack:** `uv` tool manager (already installed, v0.11.6), Claude Code CLI, Serena MCP v1.1-develop branch, Windows 11 + Git Bash.

---

## Context

### Why migrate

Current install (2026-04-10) uses `uvx -p 3.13 --from git+https://github.com/oraios/serena@v1.1-develop serena ...`. This was correct at the time: (a) the cold-start penalty is paid once per MCP session which doesn't matter for long-lived MCP servers, (b) uvx auto-refreshes when the develop branch moves forward, (c) rollback is trivial.

The situation changed on 2026-04-11 with two new facts:

1. **`serena-hooks` was announced** (news/20260411.html in the oraios/serena repo). It is a CLI invoked fresh on every hook event. With `uvx`, every invocation pays the ~0.93s cold-start — measured empirically, not estimated. For a `PreToolUse` hook that runs on every tool call, this is impractical (30-100 seconds of latency per session).
2. **Trial validated and kept** (2026-04-11, this session). The user decided to keep Serena. "Production install" now fits better than "trial install".

### What we give up

`uv tool install` does NOT auto-refresh when the `v1.1-develop` branch advances. To pull new commits, run `uv tool upgrade serena` manually. This is a trade: lose auto-refresh, gain ~18× startup speedup and per-call hook viability.

### Measured costs

| Metric | Current (uvx) | Expected (uv tool install) | Delta |
|---|---|---|---|
| MCP server cold-start (per session) | ~0.93s | ~0.05s | -0.88s |
| `activate` hook invocation (per session) | ~0.93s | ~0.05s | -0.88s |
| `remind` hook invocation (per tool call) | ~0.93s → **inviable** | ~0.05s → **viable** | unlocks hook |
| `cleanup` hook invocation (per turn) | ~0.93s → **inviable** | ~0.05s → **viable** | unlocks hook |
| `auto-approve` hook (per Serena call in acceptEdits mode) | ~0.93s → **inviable** | ~0.05s → **viable** | unlocks hook |

### Scope boundary

This plan touches **only** user-scope config files under `C:\Users\Daniel\.claude\` and the uv-managed tool directory. **Zero changes to the PDFoverseer repo**, preserving trial-mode guarantees on what gets committed. The only file created inside the repo is this plan document itself.

---

## Files

| Action | File | What changes |
|---|---|---|
| Install (command) | `C:\Users\Daniel\AppData\Roaming\uv\tools\serena\` (or wherever `uv tool dir` reports) | New Serena installation with persistent binaries |
| Modify | `C:\Users\Daniel\.claude.json` | `mcpServers.serena.command`: `uvx` → `serena` (or absolute path); `args` shrinks by 4 entries |
| Modify | `C:\Users\Daniel\.claude\settings.json` | `hooks.SessionStart[0].hooks[0].command`: uvx prefix removed; Phase 2 adds `Stop`, `PreToolUse` entries |
| Modify | `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\project_serena_setup.md` | Replace "install via uvx" sections with "install via uv tool install"; document 4 hooks + rollback |
| Create | `docs/superpowers/plans/2026-04-11-serena-uv-tool-install-migration.md` | **This plan** (you are here) |

---

## Pre-flight

### Task 0: Verify prerequisites

**Files:** none (read-only checks)

- [ ] **Step 0.1: Confirm `uv` is on PATH and recent enough**

Run: `uv --version`
Expected output contains `uv 0.11.` or newer
Why: `uv tool install` for git specs is stable in 0.11.x.

- [ ] **Step 0.2: Confirm `uv tool install --help` supports the `git+` spec**

Run: `uv tool install --help 2>&1 | head -40`
Expected: help text mentions `<PACKAGE>` accepting VCS-style specs (look for "git+" or "VCS").
Why: avoid discovering mid-install that syntax is different.

- [ ] **Step 0.3: Read current MCP entry for Serena**

Run: `claude mcp get serena`
Expected output includes `Command: uvx` and `Args: -p 3.13 --from git+https://github.com/oraios/serena@v1.1-develop serena start-mcp-server --context claude-code --project-from-cwd`
Why: capture the exact current state for rollback reference.

- [ ] **Step 0.4: Snapshot `~/.claude.json` serena entry**

Run: `python -c "import json; d=json.load(open(r'C:\Users\Daniel\.claude.json')); print(json.dumps(d.get('mcpServers',{}).get('serena'), indent=2))"`
Expected: JSON object with `command: "uvx"`, `args: [...]`
Why: we'll need the exact `args` list when editing later.

- [ ] **Step 0.5: Snapshot `~/.claude/settings.json` current hook**

Read: `C:\Users\Daniel\.claude\settings.json`
Expected: contains `hooks.SessionStart[0].hooks[0].command` starting with `uvx -p 3.13 --from ...`
Why: confirm starting state before editing.

- [ ] **Step 0.6: Confirm `~/.local/bin` OR the uv tools bin dir is on PATH from Git Bash**

Run: `echo "$PATH" | tr ':' '\n' | grep -iE '\.local/bin|uv/tools'`
Expected: at least one line matches. Git Bash PATH (from previous session logs) includes `/c/Users/Daniel/.local/bin`.
Why: if uv installs to a dir not on PATH, we must use absolute paths in config.

- [ ] **Step 0.7: Pre-install, confirm no existing `serena` / `serena-hooks` binaries**

Run: `which serena 2>&1; which serena-hooks 2>&1`
Expected: both fail with "no serena in ..." / "no serena-hooks in ...".
Why: verify we start from a clean slate; any pre-existing binary is unexpected and should be investigated.

---

## Phase 1: Binary install + existing-config migration

**Outcome of Phase 1:** Serena MCP and the `activate` hook work identically to before, but ~18× faster. No new functionality added yet.

### Task 1: Install Serena via `uv tool install`

**Files:**
- Create: `C:\Users\Daniel\AppData\Roaming\uv\tools\serena\` (managed by uv)
- Create: entry points under `uv tool dir --bin`

- [ ] **Step 1.1: Run the install**

Run:
```bash
uv tool install --python 3.13 "git+https://github.com/oraios/serena@v1.1-develop"
```

Expected: download + resolve dependencies + report `Installed 2 executables: serena.exe, serena-hooks.exe` (or similar message naming the binaries).
Timing: first install ~30-90s depending on network and dependency count.

- [ ] **Step 1.2: Verify install via `uv tool list`**

Run: `uv tool list`
Expected: line `serena v1.1-develop (from git+https://github.com/oraios/serena@v1.1-develop)` with the two executables listed underneath (`- serena`, `- serena-hooks`).

- [ ] **Step 1.3: Locate the binary directory**

Run: `uv tool dir --bin`
Expected: absolute Windows path, e.g. `C:\Users\Daniel\AppData\Roaming\uv\tools\bin\` or `C:\Users\Daniel\.local\bin\`.
Why: if PATH doesn't include this dir, we need the absolute path for the config.

- [ ] **Step 1.4: Verify binaries resolve on PATH**

Run: `which serena && which serena-hooks`
Expected: both print an absolute path.

**If either `which` fails**, set variable `SERENA_BIN` and `SERENA_HOOKS_BIN` to the absolute paths from Step 1.3 (e.g. `C:\Users\Daniel\AppData\Roaming\uv\tools\bin\serena.exe`). These absolute paths will be used in Task 3 and Task 4 instead of bare `serena` / `serena-hooks`.

- [ ] **Step 1.5: Measure startup time of `serena-hooks`**

Run: `time serena-hooks --help 2>&1 | tail -5`
Expected: `real` time < 0.2s (vs. ~0.93s for uvx). Confirms the migration's main benefit.
Record the actual measured number for the memory update later.

- [ ] **Step 1.6: Smoke-test `serena start-mcp-server` responds to help**

Run: `serena start-mcp-server --help 2>&1 | head -20`
Expected: exit 0, help text listing `--context`, `--project-from-cwd`, etc.
Why: confirms the MCP entry-point binary is intact, not just the hooks one.

### Task 2: Migrate MCP entry in `~/.claude.json`

**Files:**
- Modify: `C:\Users\Daniel\.claude.json` (top-level `mcpServers.serena`)

- [ ] **Step 2.1: Read current serena entry into a variable**

Run:
```bash
python -c "import json; d=json.load(open(r'C:\Users\Daniel\.claude.json')); print(json.dumps(d['mcpServers']['serena'], indent=2))"
```
Expected: JSON object with `command: "uvx"` and the full `args` array.

- [ ] **Step 2.2: Write the new entry via Python (avoids JSON hand-editing)**

Create a one-liner Python script that loads `~/.claude.json`, replaces the `serena` entry with:

```json
{
  "type": "stdio",
  "command": "serena",
  "args": ["start-mcp-server", "--context", "claude-code", "--project-from-cwd"]
}
```

(If Step 1.4 required absolute paths, use the absolute path in `command` instead of `"serena"`.)

Run this pattern:
```bash
python -c "
import json
path = r'C:\Users\Daniel\.claude.json'
d = json.load(open(path, encoding='utf-8'))
d['mcpServers']['serena'] = {
    'type': 'stdio',
    'command': 'serena',  # or absolute path
    'args': ['start-mcp-server', '--context', 'claude-code', '--project-from-cwd']
}
json.dump(d, open(path, 'w', encoding='utf-8'), indent=2)
print('OK')
"
```
Expected output: `OK`
Why use Python instead of Edit: `~/.claude.json` is large and may contain other `mcpServers` entries; a targeted dict mutation is safer than string matching.

- [ ] **Step 2.3: Verify the new entry via `claude mcp get`**

Run: `claude mcp get serena`
Expected: `Command: serena`, `Args: start-mcp-server --context claude-code --project-from-cwd`. Status may still show `✓ Connected` from the current session's already-spawned process — that's fine, the change takes effect on next session.

- [ ] **Step 2.4: Syntactic JSON validation of the full file**

Run:
```bash
python -c "import json; json.load(open(r'C:\Users\Daniel\.claude.json')); print('valid')"
```
Expected: `valid`. If this fails, restore from Step 2.1's snapshot and investigate.

### Task 3: Migrate existing `activate` hook in `~/.claude/settings.json`

**Files:**
- Modify: `C:\Users\Daniel\.claude\settings.json` (`hooks.SessionStart[0].hooks[0].command`)

- [ ] **Step 3.1: Edit the hook command**

Use the Edit tool to replace:

```
uvx -p 3.13 --from git+https://github.com/oraios/serena@v1.1-develop serena-hooks activate --client=claude-code
```

with:

```
serena-hooks activate --client=claude-code
```

(Or the absolute path if Step 1.4 required it.)

- [ ] **Step 3.2: Validate JSON**

Run:
```bash
python -c "import json; d=json.load(open(r'C:\Users\Daniel\.claude\settings.json')); print('valid, hooks=', list(d['hooks'].keys()))"
```
Expected: `valid, hooks= ['SessionStart']`

- [ ] **Step 3.3: Smoke-test the new hook invocation**

Run:
```bash
echo '{"session_id": "phase1-test", "hook_event_name": "SessionStart"}' | serena-hooks activate --client=claude-code
```
Expected: single-line JSON output `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "**IMPORTANT**: Activate the current working directory as project using Serena's tools..."}}`
Exit code 0.
If it fails: the command path is wrong — try with absolute path.

### Task 4: Phase 1 checkpoint — user restart

- [ ] **Step 4.1: [USER ACTION] Fully exit Claude Code**

The currently running Claude Code session still holds a reference to the old `uvx`-spawned Serena MCP subprocess. The migration only takes effect on the next session.

Close Claude Code completely (not just the window — the extension host if running in VSCode).

- [ ] **Step 4.2: [USER ACTION] Reopen Claude Code in a PDFoverseer directory**

Start a fresh session with cwd `a:/PROJECTS/PDFoverseer/` (or any subdirectory).

- [ ] **Step 4.3: [USER ACTION, then Claude] Verify three things**

In the new session, the agent verifies:

1. **MCP connected**: `claude mcp list` shows `serena: ✓ Connected`
2. **SessionStart hook fired**: the agent's initial context contains the injected `**IMPORTANT**: Activate the current working directory...` message from the hook. (If the hook didn't fire, the injected text is absent and we need to debug.)
3. **Serena tools work**: one simple tool call succeeds, e.g. `mcp__serena__list_memories` or `mcp__serena__check_onboarding_performed`.

**Success criteria for Phase 1:**
- All 3 checks pass
- Startup noticeably faster (subjective, but user will notice)
- No error messages in the Claude Code MCP debug log

**If Phase 1 fails:** stop here. Execute the Rollback section below. Phase 2 is blocked until Phase 1 is stable.

---

## Phase 2: Add `cleanup` + `remind` + `auto-approve` hooks

**Outcome of Phase 2:** full anti-drift enforcement as designed by Serena. The agent will be nudged toward symbolic tools when it leans too hard on Grep/Read, and Serena edit tools will auto-approve in `acceptEdits` mode.

**Precondition:** Phase 1 checkpoint passed. Do not run Phase 2 until the user explicitly confirms.

### Task 5: Add `cleanup` hook (Stop event)

**Files:**
- Modify: `C:\Users\Daniel\.claude\settings.json` (add `hooks.Stop` array)

- [ ] **Step 5.1: Add the Stop hook**

Use the Edit tool to add a new top-level entry inside `hooks`, after `SessionStart`:

```json
"Stop": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "serena-hooks cleanup --client=claude-code",
        "timeout": 10
      }
    ]
  }
]
```

- [ ] **Step 5.2: Validate JSON**

Run: `python -c "import json; d=json.load(open(r'C:\Users\Daniel\.claude\settings.json')); print('hooks=', list(d['hooks'].keys()))"`
Expected: `hooks= ['SessionStart', 'Stop']`

- [ ] **Step 5.3: Smoke-test the cleanup command**

Run:
```bash
echo '{"session_id": "phase2-test", "hook_event_name": "Stop"}' | serena-hooks cleanup --client=claude-code
echo "exit: $?"
```
Expected: no output (cleanup is silent when there's nothing to delete), exit 0.

### Task 6: Add `remind` hook (PreToolUse, matcher `""`)

**Files:**
- Modify: `C:\Users\Daniel\.claude\settings.json` (add `hooks.PreToolUse` array)

- [ ] **Step 6.1: Add the PreToolUse remind hook**

Use the Edit tool to add inside `hooks`, after `Stop`:

```json
"PreToolUse": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "serena-hooks remind --client=claude-code",
        "timeout": 5
      }
    ]
  }
]
```

- [ ] **Step 6.2: Validate JSON**

Run: `python -c "import json; d=json.load(open(r'C:\Users\Daniel\.claude\settings.json')); print('hooks=', list(d['hooks'].keys()))"`
Expected: `hooks= ['SessionStart', 'Stop', 'PreToolUse']`

- [ ] **Step 6.3: Smoke-test `remind` with a synthetic Grep tool call**

Run:
```bash
echo '{"session_id": "phase2-test", "hook_event_name": "PreToolUse", "tool_name": "Grep", "permission_mode": "default"}' | serena-hooks remind --client=claude-code
echo "exit: $?"
```
Expected on first call: no output (counter starts at 1, threshold is 3), exit 0.

Run the same command 2 more times to reach the threshold:
```bash
for i in 1 2 3; do
  echo '{"session_id": "phase2-test", "hook_event_name": "PreToolUse", "tool_name": "Grep", "permission_mode": "default"}' | serena-hooks remind --client=claude-code
done
```
Expected on the 3rd call: JSON output with `"permission_decision": "deny"` and `additionalContext` nudging toward symbolic tools.

- [ ] **Step 6.4: Cleanup the synthetic counter state**

Run: `rm -rf "$HOME/.serena/hook_data/phase2-test" 2>/dev/null; echo "cleaned"`
Expected: `cleaned`
Why: the smoke test left a pickle at `~/.serena/hook_data/phase2-test/tool_use_counter.pkl`; remove it so it doesn't leak into real session tracking.

### Task 7: Add `auto-approve` hook (PreToolUse, matcher `mcp__serena__*`)

**Files:**
- Modify: `C:\Users\Daniel\.claude\settings.json` (extend `hooks.PreToolUse` array)

- [ ] **Step 7.1: Add the auto-approve entry**

Edit the existing `hooks.PreToolUse` array (created in Task 6) to append a second entry. Final state:

```json
"PreToolUse": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "serena-hooks remind --client=claude-code",
        "timeout": 5
      }
    ]
  },
  {
    "matcher": "mcp__serena__*",
    "hooks": [
      {
        "type": "command",
        "command": "serena-hooks auto-approve --client=claude-code",
        "timeout": 5
      }
    ]
  }
]
```

- [ ] **Step 7.2: Validate JSON**

Run:
```bash
python -c "
import json
d = json.load(open(r'C:\Users\Daniel\.claude\settings.json'))
pre = d['hooks']['PreToolUse']
print(f'PreToolUse entries: {len(pre)}')
print(f'  [0] matcher: {pre[0][\"matcher\"]!r}')
print(f'  [1] matcher: {pre[1][\"matcher\"]!r}')
"
```
Expected:
```
PreToolUse entries: 2
  [0] matcher: ''
  [1] matcher: 'mcp__serena__*'
```

- [ ] **Step 7.3: Smoke-test auto-approve**

Run:
```bash
echo '{"session_id": "phase2-test", "hook_event_name": "PreToolUse", "tool_name": "mcp__serena__find_symbol", "permission_mode": "acceptEdits"}' | serena-hooks auto-approve --client=claude-code
```
Expected: JSON output with `"permission_decision": "allow"` and `additionalContext` mentioning auto-approval in acceptEdits mode.

Then test the negative case (non-acceptEdits mode should silently decline to output):
```bash
echo '{"session_id": "phase2-test", "hook_event_name": "PreToolUse", "tool_name": "mcp__serena__find_symbol", "permission_mode": "default"}' | serena-hooks auto-approve --client=claude-code
echo "exit: $?"
```
Expected: no output, exit 0 (the hook stays silent when not in acceptEdits mode).

### Task 8: Phase 2 checkpoint — user restart and live test

- [ ] **Step 8.1: [USER ACTION] Fully exit and reopen Claude Code**

Same as Step 4.1 / 4.2.

- [ ] **Step 8.2: [USER ACTION, then Claude] Verify all 4 hooks load**

In the new session:

1. The initial context should still contain the `activate` message (from SessionStart).
2. Issue 3 consecutive `Grep` calls for nonexistent patterns. Expected: the 3rd call returns a `deny` with a nudge to use Serena symbolic tools, and the counter resets.
3. Issue a Serena tool call (e.g. `mcp__serena__list_memories`). Expected: works normally (remind counter resets because a Serena tool was used).
4. `auto-approve` is passive in default mode — it only activates if you enter `acceptEdits` mode. Not required to test unless you want to.

**Success criteria for Phase 2:**
- All hook events fire
- `remind` nudges at the 3rd consecutive Grep
- No hook-related errors in the Claude Code log
- Session feels responsive (startup < 2s including all hooks)

---

## Post-migration: memory update

### Task 9: Update memory to reflect final state

**Files:**
- Modify: `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\project_serena_setup.md`
- Modify: `C:\Users\Daniel\.claude\projects\a--PROJECTS-PDFoverseer\memory\MEMORY.md` (index line, only if the description needs to change)

- [ ] **Step 9.1: Rewrite the "Hooks installed" section of `project_serena_setup.md`**

The current section documents only `activate` via uvx. Replace with:
- New install method: `uv tool install --python 3.13 "git+https://github.com/oraios/serena@v1.1-develop"`
- Measured new startup time (from Step 1.5)
- All 4 hooks active
- New MCP command (without uvx prefix)
- Note the manual upgrade obligation: `uv tool upgrade serena` when you want to pull latest develop commits

- [ ] **Step 9.2: Update the "Non-obvious decisions" section**

Change the first bullet from "Pinned at v1.1-develop via uvx" to reflect the new uv tool install + the rationale for why we migrated (reference this plan file by path).

- [ ] **Step 9.3: Update the rollback section**

Replace `claude mcp remove serena -s user` (which is how you roll back a uvx-based user-scope entry) with the new rollback: `uv tool uninstall serena` + revert `~/.claude.json` mcpServers.serena + revert `~/.claude/settings.json` hooks entries.

- [ ] **Step 9.4: Verify `MEMORY.md` index line is still accurate**

Read the current line:
```
- [project_serena_setup](project_serena_setup.md) — Serena MCP v1.1 validated 2026-04-11 (r/w/UTF-8 via MCP); gitignored; CLI-only gotchas + rollback
```

If it needs updating to reference the new install method, keep under 150 chars total. Otherwise leave as-is.

---

## Rollback procedure

If Phase 1 fails, or if Phase 2 causes session instability, roll back with:

### Rollback step 1: Uninstall the local binary

```bash
uv tool uninstall serena
```

Expected: `Uninstalled 1 tool: serena`.

### Rollback step 2: Restore `~/.claude.json` MCP entry

Use the same Python-mutation pattern as Step 2.2 but set the entry back to:

```json
{
  "type": "stdio",
  "command": "uvx",
  "args": [
    "-p", "3.13",
    "--from", "git+https://github.com/oraios/serena@v1.1-develop",
    "serena",
    "start-mcp-server",
    "--context", "claude-code",
    "--project-from-cwd"
  ]
}
```

Verify with `claude mcp get serena`.

### Rollback step 3: Restore `~/.claude/settings.json` hooks

Use the Edit tool to revert:
- The `activate` hook command back to the full `uvx -p 3.13 --from ...` prefix.
- If Phase 2 was started, remove `Stop` and `PreToolUse` entries entirely (restore the single-hook state from Phase 1).

Verify JSON: `python -c "import json; json.load(open(r'C:\Users\Daniel\.claude\settings.json')); print('valid')"`.

### Rollback step 4: Restart Claude Code

Same as Step 4.1 / 4.2. Verify `claude mcp list` shows `serena: ✓ Connected` and that things behave identically to before the migration.

### Rollback step 5: Update memory

Revert the "Hooks installed" section of `project_serena_setup.md` to the pre-migration state (single `activate` hook via uvx).

---

## Risks and their mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| `uv tool install` fails on a dependency (no compiler, native module build) | Low — Serena is pure Python with LSP server dependencies | High — blocks the whole plan | Run Step 1.1 in isolation first; if it fails, investigate the error before touching any config |
| Binary installed but not on PATH (uv installs to a dir not in Git Bash PATH) | Medium | Medium — mitigated by falling back to absolute paths | Step 1.4 explicitly catches this; Steps 2.2 and 3.1 accept absolute paths |
| MCP entry edit corrupts other MCP servers in `~/.claude.json` | Low — Python dict mutation is surgical | High — breaks all MCP servers | Snapshot in Step 0.4; use `json.load` + dict mutation (not string replace); validate with Step 2.4 |
| `Stop` hook fires more aggressively than expected (every turn) and causes latency | Medium — per Serena source it does fire per-turn | Low — ~0.05s × N turns is tolerable | Monitored in Phase 2 checkpoint; rollback available |
| `remind` hook incorrectly denies a legitimate Grep/Read burst | Medium — 3 consecutive calls is a low threshold | Low — the `deny` message says "counter reset, retry" so no hard lock | The agent can immediately retry; if the pattern persists, raise the thresholds by editing `hooks.py` counters (out of scope here) |
| `uv tool install` pulls a newer commit than the currently-running uvx cache, introducing a version skew between the already-running MCP subprocess and the hooks | Certain — they WILL be different commits | Low — the old subprocess dies on session restart | Phase 1 checkpoint's restart forces them into sync |
| Claude Code hook system has breaking changes in a future version | Low — API is documented | Medium | Rollback procedure documented; Claude Code hooks are versioned per settings schema |

---

## Open questions (to resolve during execution, not before)

1. **Q: Does `uv tool install` on Windows install to `~/.local/bin`, `~/AppData/Roaming/uv/tools/bin/`, or somewhere else?**
   A: resolve with Step 1.3 (`uv tool dir --bin`). This determines whether bare `serena` / `serena-hooks` works or we need absolute paths.

2. **Q: Does Claude Code's hook subsystem spawn hooks via Git Bash, cmd.exe, or PowerShell on Windows?**
   A: resolve empirically in Phase 1 checkpoint (Step 4.3). If the activate hook doesn't fire, the PATH resolution shell is likely the culprit — absolute paths fix it.

3. **Q: Does `remind`'s per-turn `Stop` cleanup cause observable lag?**
   A: resolve in Phase 2 checkpoint (Step 8.2). If lag is noticeable, move `cleanup` to a different event or drop it.

---

## Post-execution checklist

After all tasks complete and both checkpoints pass:

- [ ] `claude mcp list` shows `serena: ✓ Connected`
- [ ] `which serena-hooks` returns an absolute path
- [ ] `~/.claude/settings.json` has 4 hook entries: 1 SessionStart, 1 Stop, 2 PreToolUse
- [ ] `time serena-hooks --help` measures < 0.2s
- [ ] Memory file `project_serena_setup.md` reflects the new state
- [ ] A fresh Claude Code session successfully fires the `activate` hook and exposes all 17 Serena tools
- [ ] The PDFoverseer repo has zero tracked changes from this migration (only the plan document itself is new, and even that is optional to commit)
