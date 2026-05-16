# Work Log — BoneIO fork (M4rv-dev/app_black)

> **Read this first** when starting a new Claude Code session on this repo. It carries
> context that survives across sessions, model switches, and CLI restarts.

---

## Project overview

This is a **fork** of `boneIO-eu/app_black` maintained at `github.com/M4rv-dev/app_black`. The upstream
ships v1.4.0dev2; we extend it with the **expansion-board** feature (adding I²C MCP23017
expanders that double available outputs). The goal is to ship features upstream **doesn't have**,
while staying mergeable with their releases.

### Topology

| Remote | URL | Access |
|--------|-----|--------|
| `origin` | github.com/boneIO-eu/app_black | read-only (upstream) |
| `fork` | github.com/M4rv-dev/app_black | push (our fork) |

| Branch | Purpose |
|--------|---------|
| `dev-debian13` | Tracks upstream main; our base for merges |
| `feat/expansion-board` | Active feature branch (current) |

### Deployment

- **Target device**: BoneIO @ `192.168.1.22` (BeagleBone Debian 13, user `boneio`)
- **Deploy script**: `./deploy_backend.sh` (gitignored, contains password). Rsyncs the whole
  `boneio/` Python package to `/home/boneio/boneio/venv/lib/python3.13/site-packages/boneio/`,
  then restarts `boneio.service`.
- **Frontend**: Vite dev server at `localhost:5173` (proxies to device's API on `:8090` and
  Caddy/Node-RED on `:8091`). `.env.local` has `VITE_API_URL` + `VITE_NODERED_URL`.
- **Web UI on device**: direct Hypercorn on `:8090` OR via Caddy proxy on `:8091` (Caddy proxies
  BoneIO UI + provides Node-RED at `/nodered/`). For Node-RED tab to appear, use `:8091`.

---

## Architecture decisions

### Module pattern (CORE PRINCIPLE)

**BoneIO upstream is treated as core engine; our extensions live in dedicated `modules/` folders
with strict public APIs.** Touching upstream files is allowed only for 1 import + 1-2 use lines.

Why: BoneIO will keep releasing 1.4.x / 1.5; embedding logic in their files = merge conflicts
on every release. The module pattern keeps our merge surface minimal.

```
frontend/src/components/UISettings/modules/<feature>/
├── index.ts            ← public API — upstream imports only from here
├── components/         ← Presentational (sam render)
├── hooks/              ← stateful + side-effects + fetch
├── helpers/            ← pure functions
├── types/              ← TypeScript types
└── constants/

boneio/modules/<feature>/
├── __init__.py         ← public API
├── yaml_util.py        ← pure helpers
└── routes.py           ← endpoints + register_routes(app)
```

### Future re-skin (NOT in current scope)

A future project will provide an alternative UI as a **wrapper layer** over both boneIO
components AND our modules — written as additional modules, never modifying existing code.
Our modules MUST keep logic in hooks/helpers (not in components) so the re-skin can swap
components without touching logic.

### Memory & plans

- **Memory dir**: `~/.claude/projects/-Users-mariuszskupinski-Documents-BoneIO-app-black/memory/`
  (`MEMORY.md` index auto-loaded by Claude)
- **Active plan**: `~/.claude/plans/boardy-s-takie-jakie-starry-sun.md` (the modules refactor)

---

## Active scope

**Current task**: Refactor expansion-board feature into `modules/expander/` pattern.

**Why**: After merging upstream v1.4.0dev2 (commit `fbe2140`), audit revealed our code is scattered
across 7+ upstream files. Each future upstream release will conflict on the same spots. Module
pattern eliminates that.

**Phase status** (granular commits, easy to revert each):

| # | Phase | Status |
|---|-------|--------|
| 0a | Scaffold modules/expander/ + types + constants + index.ts | ✅ |
| 0b | Move expanderBoards + outputMcpUtils into module; add isExpanderOutput + getOutputStats; shim old paths | ✅ |
| 0c | Backend scaffold `boneio/modules/expander/` + yaml_util.py + routes.py + register in app.py | ✅ |
| A1 | Extract `useExpanderManager` + `<ExpanderManager />` from `BoneIOForm.tsx` | ✅ |
| A2 | Extract `useMcpHardware` + `<McpHardwareFields />` from `OutputForm.tsx` | ✅ |
| A3 | Extract `useOutputCapacity` + `<OutputAddButton />` from `ArrayTableWidget.tsx` | ✅ |
| A4 | Derive `outputKind` via `useOutputKind` (drop useState) | ✅ |
| B | Dedupe EX_ detection, MCP addresses, remove dead `onExpanderAdded` prop | ✅ |
| — | Verify (tsc + build + python smoke + anti-duplicate greps) | ✅ |
| — | Deploy + manual smoke test in UI | ✅ deployed; UI smoke test confirmed working by user |
| Future | Build/inject script POC (auto-apply modules onto fresh upstream) | 📋 idea, deferred |

---

## Timeline

### 2026-05-15 → 2026-05-16 — Session 1 (upstream merge + module refactor)

**Goal**: Catch up with upstream v1.4.0dev2 (was 14 commits behind), preserve our expansion-board
work, then refactor for future-merge friendliness.

**Done**:
- ✅ Configured git: `.gitignore` for `deploy_backend.sh` (password) + `.DS_Store`
- ✅ Created `feat/expansion-board` branch
- ✅ 5 thematic local commits before merge (backend split-write, BoneIO settings UI, OutputForm with
  TabsBox, UI polish, translations)
- ✅ Merged upstream `dev-debian13` → 6 manual conflict resolutions:
  - `ArrayTableWidget.tsx` — kept upstream's `FormRenderer` dispatch, extended with `outputKind`+`mcp23017` props
  - `UISettings.tsx` — kept hex-string normalization for mcp23017 addresses (over upstream's integer-only)
  - `SectionContent.tsx` — kept both `mcp23017` (ours) + `allRemoteInputs` (upstream) props
  - `FormRenderer.tsx` — extended to forward `outputKind` + `mcp23017` to OutputForm
  - `helpers/itemValidation.ts` — extended with `getOutputStats` + expander capacity logic
- ✅ Merge commit `fbe2140` on `feat/expansion-board`
- ✅ TypeScript clean, frontend build clean, Python import smoke ok
- ✅ Installed `gh` CLI, forked upstream to `M4rv-dev/app_black`, pushed branch
- ✅ Rewrote `deploy_backend.sh` to rsync full `boneio/` package (instead of just 2 files)
- ✅ Deployed to BoneIO device: now running 1.4.0dev2 (was 1.3.1)
- ✅ Hypercorn responds 200 on `:8090`, Caddy proxy on `:8091` works for Node-RED
- ✅ Diagnosed missing Node-RED tab in dev: fixed by adding `VITE_NODERED_URL=http://192.168.1.22:8091` to `.env.local`

**Architecture audit** (after merge, before module refactor):
- 3 critical: BoneIOForm (577 lines, ~120 of ours), OutputForm (994 lines, ~150 inner McpHardwareFields), yaml_util.py (split-write embedded ~70 lines)
- 5 duplications: `startsWith('EX_')` × 6 in 5 files, `ADDRESS_OPTIONS` × 2, include-pattern regex × 2 Python, `getOutputStats` IIFE in JSX, `useState outputKind` (should be derived)
- Missing types: `any[]` in 5 files
- Dead code: `BoneIOForm.tsx:37` deprecated `onExpanderAdded` prop

**Plan**: Modules pattern refactor — see `~/.claude/plans/boardy-s-takie-jakie-starry-sun.md`.

**Refactor — completed end-to-end**:
- All phases (0a → B) implemented, verified, committed (7 granular commits), pushed to `fork/feat/expansion-board`, and deployed to BoneIO @ 192.168.1.22.
- Frontend `modules/expander/`: 14 files, ~1065 lines (4 components + 4 hooks + 2 helpers + 3 types + 1 constants + index.ts).
- Backend `boneio/modules/expander/`: 3 files, ~351 lines (yaml_util.py + routes.py + __init__.py with lazy FastAPI import via `__getattr__`).
- BoneIO files slim-down: 7 upstream files lost 657 lines total (–205 in BoneIOForm, –161 in OutputForm, –177 in routes/config.py, etc.). Each retains only 1-2 import + use lines pointing to module.
- Deploy verified: BoneIO 1.4.0dev2 active on device, Hypercorn :8090 returns HTTP 200, `POST /api/config/expander[/remove]` registered (return 422 for empty body — module routes wired correctly), ESPHome connections wstają, expander chips widoczne w display screen list.
- Anti-duplicate checklist 100% clean (no `startsWith('EX_')` outside module, no duplicated MCP address arrays, no inline include-pattern regex, no `useState outputKind`, no `any[]` in module files).

**Commits on this branch since merge `fbe2140`**:
- `96d79b0` — scaffold modules/expander/ + move helpers into module
- `4fe90a0` — scaffold boneio/modules/expander/ backend + slim upstream
- `d2d6d1e` — extract useExpanderManager + <ExpanderManager />
- `a6755ae` — extract useMcpHardware + <McpHardwareFields />
- `bad59e3` — extract OutputAddButton + derive outputKind via hook
- `2eadc44` — dedupe Mcp23017Form constants + OutputTable EX_ check
- `869b32e` — add WORK_LOG.md

**Pending (next session)**:
- Optional: build/inject script POC (task #22) — auto-apply modules onto fresh upstream pull. Pattern now proven on hardware → worth doing when next upstream release lands.
- Eventually: alternative UI skin layer (re-skin) using the same module hooks/helpers.

**Outcome — module pattern validated end-to-end**:
The modules/ pattern works in practice. Future upstream merges should produce minimal conflicts (only the 1-2 line injection points per file). Each subsequent feature should follow the same template: `frontend/.../modules/<feature>/` + `boneio/modules/<feature>/` with public API via `index.ts` / `__init__.py`.

---

## Runbook — next upstream merge

When boneIO releases the next dev tag (1.4.0dev3, 1.4.0, 1.5.x …), follow this. The
goal: pull their changes, re-apply ours, deploy, ship — without re-inventing the wheel.

### Step 1 — pull upstream

```bash
git checkout dev-debian13
git pull origin dev-debian13            # fast-forwards to upstream HEAD
git log --oneline HEAD ^feat/expansion-board | head -30   # what's new
```

### Step 2 — merge into our feature branch

```bash
git checkout feat/expansion-board
git merge dev-debian13                   # produces merge commit; expect SMALL conflicts
git status                               # see unmerged paths
```

### Step 3 — resolve conflicts (the predictable ones)

Conflicts will almost always land at our **7 injection sites**. For each, the goal
is to **keep upstream's new structure** and **re-apply our 1-2 line injection** in
the right place. Our injection points are marked by comments — search for them:

| File | Our injection (marker to look for) |
|------|-------------------------------------|
| `frontend/.../BoneIOForm.tsx` | `import { ExpanderManager } from './modules/expander';` + `<ExpanderManager allOutputs={...} />` after `{/* Expansion board — fully encapsulated module */}` |
| `frontend/.../OutputForm.tsx` | `import { McpHardwareFields, EXPANDER_BOARDS, EXPANDER_OUTPUT_PREFIX, isExpanderOutput, type ExpanderBoardType } from './modules/expander';` + `<McpHardwareFields ... />` call |
| `frontend/.../ArrayTableWidget.tsx` | `import { OutputAddButton, isExpanderOutput, useOutputKind, EXPANDER_OUTPUT_PREFIX } from './modules/expander';` + `<OutputAddButton ... />` + `const outputKind = useOutputKind(editingItem);` |
| `frontend/.../Mcp23017Form.tsx` | `import { MCP_ADDRESS_OPTIONS, MANAGED_EXPANDER_IDS, DEFAULT_ADDRESSES, DEFAULT_ADDRESS_INTEGERS, isExpanderOutput, ... } from './modules/expander';` |
| `frontend/.../helpers/itemValidation.ts` | `import { getOutputStats, isExpanderOutput } from '../modules/expander';` + `isExpanderOutput(dataToSave)` in output validation |
| `frontend/.../tables/OutputTable.tsx` | `import { isExpanderOutput } from '../modules/expander';` + `isExpanderOutput(item)` for badge |
| `frontend/.../components/SectionContent.tsx` | Just `mcp23017` prop passed through to BoneIOForm (no expander call here) |
| `boneio/core/config/yaml_util.py` | `from boneio.modules.expander import split_outputs_for_includes, dedup_outputs_prefer_named` + the 4-line split-write block in `update_config_section()` |
| `boneio/webui/app.py` | `from boneio.modules.expander import register_routes as register_expander_routes` + `register_expander_routes(app)` at end of router registration |
| `boneio/webui/routes/config.py` | Nothing (endpoints moved to module) — if upstream re-introduces an expander endpoint there, decide whether to remove and keep ours |

Tip: `git diff fbe2140..HEAD -- <file>` shows exactly what our refactor put there.

### Step 4 — verify with the anti-duplicate checklist

After resolving conflicts, run these greps to catch any inline duplicates upstream
might have re-introduced (e.g. a fresh `startsWith('EX_')` they added):

```bash
# Must return empty (with the SHIM files exception in #2 — that's intentional)
grep -rn "startsWith.*EX_\|startswith.*EX_" frontend/src/ boneio/ \
  --include="*.ts" --include="*.tsx" --include="*.py" 2>/dev/null \
  | grep -v "modules/expander" | grep -v "__pycache__"

grep -rn "'0x20'.*'0x21'.*'0x22'" frontend/src/ \
  --include="*.ts" --include="*.tsx" 2>/dev/null \
  | grep -v "modules/expander"

grep -rn "^output:.*!include" boneio/ --include="*.py" 2>/dev/null \
  | grep -v "modules/expander" | grep -v "__pycache__"

grep -rn "useState.*outputKind\|setOutputKind" frontend/src/ \
  --include="*.ts" --include="*.tsx" 2>/dev/null

grep -rn "any\[\]" frontend/src/components/UISettings/modules/ \
  --include="*.ts" --include="*.tsx" 2>/dev/null
```

If anything new pops up, fix it (replace with module helper) before committing.

### Step 5 — build chain

```bash
cd frontend && npx tsc --noEmit && npm run build
cd .. && python3 -c "from boneio.bonecli import main; print('bonecli ok')"
python3 -c "from boneio.modules.expander.yaml_util import is_expander_output; print('module ok')"
```

### Step 6 — finalise merge commit

```bash
git commit                # opens editor with merge message; summarise conflicts resolved
git push fork feat/expansion-board
```

### Step 7 — deploy + smoke test

```bash
./deploy_backend.sh                              # full rsync of boneio/ + service restart
sshpass -p '...' ssh boneio@192.168.1.22 "systemctl is-active boneio.service"
curl -sS http://192.168.1.22:8090/ -o /dev/null -w "HTTP %{http_code}\n"
```

Then in UI (`localhost:5173`): regression suite — Add/Remove Expander, edit EX_OUT_*,
badge "expander", dropdown counters, plus a quick poke at any NEW upstream features
to confirm they work.

### Edge cases the module pattern still can't dodge

1. **Upstream renames a file we inject into.** Git marks it as renamed+modified, our
   injection lands in the wrong place or gets dropped. Recovery: `git log --follow`
   the old path, re-apply the injection to the new file.
2. **Upstream changes a function signature we depend on** (e.g. `update_config_section()`
   gets new args). Our backend module helper call breaks. Recovery: adapt the module's
   call site to the new signature; the module's INTERNAL logic stays unchanged.
3. **Upstream ships their own version of our feature** (e.g. their own expander UI).
   Decide: remove ours, merge concepts, or keep both with namespacing. Module isolation
   makes "remove ours" trivial (`rm -rf modules/expander/` + revert injection lines).
4. **Upstream changes Cerberus schema in a way that rejects our EX_* outputs**. Recovery:
   add schema overrides in `boneio/modules/expander/schema_patches.py` (new file, not
   yet built) and apply during boot.

### Threshold for investing in build/inject automation (task #22)

Stop doing manual merges and build the inject script if **any of**:
- More than 2 of our 7 injection points conflict in a single upstream release
- Upstream renames an injection-point file (high-friction recovery)
- We add a 2nd module (e.g. cloud_sync) — automation amortises across modules
- We start managing 3+ branches (e.g. dev + stable backport)

Until then: manual merges with this runbook are cheaper than maintaining a patch system.

---

## How to update this log

After each meaningful work block (typically end of a session, or when finishing a phase):

1. **Update "Active scope"** — current task, phase status table
2. **Append to "Timeline"** — new dated entry with:
   - Goal of the session
   - What was done (✅ bullets)
   - Any decisions made / patterns introduced
   - Current state at end (so next session picks up cleanly)
3. **Mention any new files of architectural significance** in "Architecture decisions"
4. **Don't delete history** — append, don't rewrite. Old entries are evidence of why decisions were made.

Update this file **even if user didn't ask** — it's the persistent context source. Memory pointer
to it in `~/.claude/projects/.../memory/project_work_log.md`.
