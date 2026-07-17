# GeuseMaker TUI Rollout — Brutalist Hybrid UI

**Status:** Implemented — operational TUI screens, shared configuration seam, and live log streams shipped (Phase 5 complete 2026-07-17); wizard polish (§7) remains

**Audience:** Contributors implementing wizard polish + optional full-screen Textual app

**Captured:** 2026-07-15

**Implementation alignment:** 2026-07-16
**Related:** Epic 8 (interactive mode), `geusemaker/cli/branding.py`, `geusemaker/cli/components/`, `geusemaker/cli/interactive/`

---

## 1. Goal

Ship a **modern, brutalist** terminal experience with two shells over the same Python services:

| Shell | Default? | Stack | Purpose |
|-------|----------|-------|---------|
| **Wizard** | Yes | Click + Rich + questionary | Guided deploy, scrollback-friendly, CI-safe |
| **Full TUI** | Opt-in | Textual 8.x | Operations shell today; multi-pane status, deploy, and monitoring are rollout targets |

Non-goals: Go rewrite, replacing Click for non-interactive commands, making Textual required for CI.

**NFR constraint:** ≥ 90% of operations remain callable non-interactively (JSON/YAML machine output unchanged).

---

## 2. Version baseline (verified 2026-07-15)

Queried via PyPI + Textualize docs (Context7 / GitHub / PyPI).

| Package | Current GeuseMaker pin | Latest stable | Rollout target |
|---------|------------------------|---------------|----------------|
| **textual** | `>=8.2,<9` in optional `[tui]` extra | **8.2.8** (2026-06-30) | Implemented |
| **rich** | `>=14.2,<16` | **15.0.0** (2026-04-12) | Implemented |
| **questionary** | `>=2.1,<3` | **2.1.1** | Implemented |
| **click** | `>=8.1` | **8.4.2** | `click>=8.1,<9` (keep; bump floor optional to `>=8.2`) |
| **prompt-toolkit** | (transitive via questionary) | **3.0.52** | leave transitive |

### Install shapes

```toml
# pyproject.toml (implemented shape)
dependencies = [
  "click>=8.1",
  "rich>=14.2,<16",
  "questionary>=2.1,<3",
  # ... existing ...
]

[project.optional-dependencies]
tui = ["textual>=8.2,<9"]
```

```bash
pip install -e ".[dev]"       # wizard path only
pip install -e ".[dev,tui]"   # wizard + full-screen app
```

**Hard rule:** `geusemaker/services/` and `geusemaker/orchestration/` must not import Textual or questionary.

---

## 3. Research summary — modern TUI trends (2026)

### 3.1 Framework practice (Textual 8)

From [Textual docs](https://textual.textualize.io/) / layout how-to:

- Sketch layout first; **dock** header/footer/sidebar before flexible `1fr` body.
- Style with **TCSS** + semantic theme variables (`$primary`, `$surface`, `$foreground`, footer key tokens).
- Prefer **workers / `asyncio.to_thread`** for boto3; update only changed widgets (1–2 Hz for status, not 60 fps).
- Keep Click/Typer for CLI entry; Textual wraps operational workflows (industry pattern: CLI shell + TUI app).

### 3.2 Brutalist / monospace aesthetic (2026)

Aligned with terminal brutalism + [Monospace Design TUI](https://github.com/coreyt/monospace-design-tui) ideas:

| Do | Don't |
|----|-------|
| High contrast, near-black surface, sharp box-drawing borders | Soft cards, heavy gradients, glow |
| Uppercase labels, bracketed badges `[OK]`, fixed-width metrics | Pill clusters, emoji as the only hierarchy |
| Zero radius, heavy/double Unicode borders (`┏┓`, `╠═`) | Rounded McGugan-only chrome everywhere |
| Sparse 8-row rhythm; one job per pane | Dense dashboard soup in the first viewport |
| Abrupt focus states (invert / heavy border) | Animated shadows, purple neon kitsch |

**GeuseMaker-specific palette (proposed “phosphor brutalist”):**

| Token | Hex / Rich style | Use |
|-------|------------------|-----|
| `$surface` | `#0a0c0f` | App background |
| `$panel` | `#12151a` | Panes |
| `$ink` | `#e8ecef` | Primary text |
| `$muted` | `#6b7280` | Help / dim |
| `$signal` | `#c8f542` | Primary action / success rail (acid lime, not purple) |
| `$warn` | `#f5a524` | Amber warnings |
| `$fault` | `#ff4d4d` | Errors |
| `$rule` | `#2a3038` | Borders / grid seams |

Map the same tokens into Rich `Theme({...})` for the wizard so both shells feel like one brand.

### 3.3 Accessibility

- Keep WCAG-ish contrast for body text even when the look is “raw.”
- Visible focus rings (heavy border / invert).
- ASCII-safe fallbacks when `NO_COLOR` / dumb terminals / `--silent`.
- Stage glyphs must degrade to `[VPC]`-style tags when Unicode box-drawing is unavailable.

---

## 4. Branding — ASCII as trademark + stage marks

### 4.1 Trademark / hero banner (keep)

Preserve existing art in `geusemaker/cli/branding.py` as the product mark:

- **`MAIN_BANNER`** — shown on bare `geusemaker` (CLI root). This is the **trademark logo**.
- **`DEPLOY_BANNER`** — shown at start of interactive/visual deploy. Keep block-letter GEUSE + MAKER; restyle colors to brutalist tokens (signal lime + ink) instead of cyan/magenta defaults.
- **`COMPACT_BANNER`** — non-TTY / machine-adjacent one-liner.

In the Textual app: render `MAIN_BANNER` (or a slightly trimmed variant) once in the **Header** / splash screen — not on every pane refresh.

### 4.2 Stage glyphs (new) — small, detailed, log-prefixed

Add a second asset set: **compact ASCII marks** printed once when each deployment/orchestration stage **starts** in wizard logs (and mirrored as a Static label in the TUI timeline).

Design constraints:

- Max **5 lines × ~12–16 cols** (must not dominate scrollback).
- More detailed than a single emoji; less loud than `DEPLOY_BANNER`.
- Prefix every stage start with glyph + `STAGE · NAME` uppercase label.
- Skip glyphs entirely when `VerbosityLevel.SILENT` or machine output.

#### Proposed stage catalog

| Stage key | When | Suggested mark (illustrative; finalize in implementation) |
|-----------|------|-----------------------------------------------------------|
| `validate` | Pre-deploy validation | Checklist block |
| `vpc` | VPC / subnet resolve | Small network diamond |
| `sg` | Security group | Shield / lock grid |
| `efs` | EFS create / mount prep | Disk / cylinder |
| `iam` | Role + instance profile | Key / badge |
| `ec2` | Instance launch | Server brick |
| `spot` | Spot selection / fallback | Bolt in bracket |
| `userdata` | UserData / SSM log stream | Scroll / tape |
| `alb` | Tier 2 ALB | Horizontal bar / arrows |
| `cdn` | Tier 3 CloudFront | Globe / edges |
| `health` | Health checks | Pulse / heartbeat |
| `finalize` | Success summary | Stamp / seal |

Example log shape (wizard):

```text
┌──┐
│≡≡│  STAGE · EFS
└──┘  Creating filesystem fs-… (Stack=nga)

┌▓▓┐
│██│  STAGE · EC2
└▓▓┘  Launching g4dn.xlarge spot in us-east-1b
```

Implementation sketch:

```python
# geusemaker/cli/branding.py (planned)
STAGE_GLYPHS: dict[str, str] = {
    "efs": r"""┌──┐
│≡≡│
└──┘""",
    "ec2": r"""┌▓▓┐
│██│
└▓▓┘""",
    # ...
}

def print_stage(stage: str, message: str) -> None:
    """Emit glyph + STAGE label; no-op in silent/machine modes."""
```

Orchestrators / `DeploymentRunner` emit stages via a **`ProgressEvent`** callback (see §6) — never by importing Rich into services.

---

## 5. Target architecture

```
Click (entry / flags / CI)
├── Wizard shell (default)
│   ├── Rich Theme (brutalist tokens)
│   ├── Dialogs + questionary (polished)
│   └── Stage glyphs in scrollback logs
├── TUI shell (--tui / geusemaker tui)
│   ├── Textual App + TCSS
│   ├── Screens: Hub, Deploy, Monitor, Inspect
│   └── Same ProgressEvent stream → panes
└── Machine output (json/yaml) — unchanged

Shared domain (no UI imports):
  DeploymentDraft / ConfigBuilder (cli/configuration/ — implemented 2026-07-17)
  InteractiveFlow (wizard adapter; delegates config construction to ConfigBuilder)
  DeploymentRunner + ProgressEvent
  Tier*Orchestrator, services, StateManager
```

### Entry points

```bash
geusemaker deploy                 # wizard (default)
geusemaker deploy --tui           # full-screen deploy (requires [tui])
geusemaker tui                    # operational hub: deploy / monitor / inspect (logs via Inspect `l`)
geusemaker monitor start STACK --tui  # opens the live monitor workspace
GEUSEMAKER_UI=tui geusemaker deploy … # supported by deploy
GEUSEMAKER_UI=tui geusemaker monitor start STACK  # supported by monitor start
```

`deploy --tui` and `monitor start --tui` route into operational Textual
workspaces (a `ConfigBuilder`-backed deploy form and a live health monitor).
`GEUSEMAKER_UI` is not a global CLI switch; only commands that explicitly
inspect it support the override.

If `[tui]` missing: clear error → `pip install 'geusemaker[tui]'`.

---

## 6. Shared progress contract (critical seam)

Extract before building Textual (Phase 2). Both shells consume the same events.

```python
# implemented: geusemaker/cli/progress_events.py
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Stage = Literal[
    "validate", "vpc", "sg", "efs", "iam", "ec2", "spot",
    "userdata", "alb", "cdn", "health", "finalize",
]

@dataclass(frozen=True)
class ProgressEvent:
    stage: Stage
    message: str
    level: Literal["debug", "info", "warn", "error"] = "info"
    resource_id: str | None = None
    ts: datetime | None = None
```

- `DeploymentRunner` and the tier orchestrators emit the full granular stage
  stream (vpc/sg/efs/iam/ec2/spot/userdata/alb/cdn/health/finalize) with resource
  IDs and error events (done 2026-07-16) — the stream is a complete deployment timeline.
- Wizard adapter: print stage glyph + Rich line.
- Textual adapter: append to `RichLog` / update timeline widget.
- Tests: assert event sequence with a recording callback (no TTY needed).

---

## 7. Wizard polish (Track A)

Touch points (existing seams — keep them):

| Module | Role |
|--------|------|
| `cli/components/dialogs.py` | All prompts; questionary selects |
| `cli/interactive/prompts.py` | Domain defaults |
| `cli/interactive/flow.py` | Step order / resume |
| `cli/components/theme.py` | Expand to brutalist `ColorTheme` + Rich `Theme` |
| `cli/branding.py` | Banners + `STAGE_GLYPHS` |

### Polish checklist

- [ ] Step chrome: `STEP · INSTANCE` uppercase, muted help under prompt. If a
      numeric counter is shown, compute it from the conditional visible steps;
      `InteractiveFlow` currently defines 13 internal steps.
- [ ] Shared questionary `Style` mapped from brutalist tokens (hex only)
- [ ] Searchable / scrollable selects for long VPC/subnet/AMI lists
- [ ] Consistent Esc/back/quit via `DialogBack` / `DialogAbort`
- [ ] Pre-launch review panel with hard borders (no soft cards)
- [ ] Stage glyphs on validate → finalize
- [ ] Fold remaining `click.prompt` / `click.confirm` in destroy/rollback into `Dialogs`
- [ ] Resume menu: resume / restart / export YAML

Wizard stays linear and scrollback-friendly — **do not** embed the wizard inside Textual unless a later epic explicitly merges them.

### Required wizard/TUI configuration seam

**Status: implemented (2026-07-17).** `geusemaker/cli/configuration/` provides
`DeploymentDraft` (fields mirrored reflectively from `DeploymentConfig`) and
`ConfigBuilder` (defaults, quick-mode presets, conditional `visible_fields()`,
per-field `validate()`, `build()`, YAML round-trip). `InteractiveFlow._build_config`
and the wizard YAML export both delegate to it — this also fixed a bug where the
wizard silently dropped nine prefilled fields (budget_limit, enable_alb/cdn,
runtime bundle, cert ARNs, rollback settings). Wizard-parity tests assert both
adapters produce identical `DeploymentConfig` objects. The Textual deploy form
builds on this layer; TUI YAML import remains for the deploy screen.

The extracted model:

```text
Wizard prompts ─┐
                ├─> DeploymentDraft / ConfigBuilder ─> DeploymentConfig
Textual forms ──┘                │
                                 ├─> discovery and validation results
                                 └─> YAML import/export

DeploymentConfig ─> DeploymentRunner ─> ProgressEvent stream
```

The shared layer should own defaults, conditional field visibility, validation,
discovery selections, serialization, and `DeploymentConfig` construction. The
wizard retains back/abort/resume behavior; Textual owns form focus and screen
navigation. Both adapters should be tested against the same configuration
fixtures so they cannot silently produce different deployments.

---

## 8. Full-screen Textual app (Track B)

### 8.1 Layout (dock-first)

```
┌─────────────────────────────────────────────────────────┐
│ HEADER  MAIN_BANNER (1–2 lines trimmed) + stack/region  │  dock top
├──────────────┬──────────────────────────────────────────┤
│ SIDEBAR      │ BODY (1fr)                               │
│ [Deploy]     │  left: checklist / steps                 │
│ [Monitor]    │  right: live log + cost                  │
│ [Inspect]    │                                          │
│ [Logs]*      │                                          │
├──────────────┴──────────────────────────────────────────┤
│ FOOTER  key bindings  │  spot/on-demand  │  last event  │  dock bottom
└─────────────────────────────────────────────────────────┘
```

`*` Logs is implemented as a screen reached from Inspect (`l`), not a sidebar
entry; Status remains a target view. The sidebar exposes Hub, Deploy, Monitor,
and Inspect.

### 8.2 Screens (delivered)

1. **Monitor** — DONE: health table + event log driven by an async polling worker
2. **Inspect** — DONE: resource inventory (a dedicated Status view was folded into Inspect)
3. **Deploy** — DONE: form backed by `DeploymentDraft`/`ConfigBuilder` with YAML
   import/export, feeding a `ProgressEvent`-driven timeline (`DeployRunScreen`)
4. **Hub** — DONE: `geusemaker tui` landing

### 8.3 Textual implementation notes

- Each operational mode is a `Screen` class (`InspectScreen`, `MonitorScreen`,
  `DeployScreen`, `DeployRunScreen`, `LogsScreen`) pushed over the hub;
  `CSS_PATH = "brutalist.tcss"` plus shared `theme.py` tokens.
- `border: heavy` / `tall`; background `$surface`; accent `$signal`
- AWS calls in workers; UI thread only applies events
- Bindings: `q` quit, `?` help, `tab` focus cycle, `d` deploy, `m` monitor
- Do not redraw whole screen on each SSM line — append to `RichLog`

### 8.4 Log streaming contract (TUI wiring)

Three distinct streams feed the TUI. Each has its own source, transport, and
readiness today. All of them follow the same worker rules (below); none of them
change the machine-output (json/yaml) contract.

| Stream | Source | Transport | Status today |
|--------|--------|-----------|--------------|
| Deployment progress | `DeploymentRunner` + tier orchestrators | `ProgressEvent` callback (in-process) | Implemented (orchestrator events + `DeployRunScreen` timeline) |
| Deployment userdata log | `/var/log/geusemaker-userdata.log` | `SSMService.stream_userdata_logs()` generator, 2s poll | Implemented (CLI `logs --follow` + `DeployRunScreen` attach) |
| Instance (server-side) logs | `/var/log/geusemaker/model-preload.log`, `/var/log/amazon/efs/mount.log`, syslog/journal | SSM `tail -c` polling | Implemented (`SSMService.tail_file()`, Logs screen) |
| Docker container logs | n8n, ollama, qdrant, crawl4ai, postgres | SSM `docker logs --since` polling | Implemented (`SSMService.follow_container_logs()`, Logs screen + CLI `--follow` parity) |

**Expectations per stream:**

1. **Deployment (Deploy screen).** The deploy checklist is driven by
   `ProgressEvent` (stage timeline + glyph per stage); when the `userdata`
   stage begins, the screen additionally attaches
   `stream_userdata_logs(instance_id)` and appends lines to the log pane until
   the completion marker, error guard, or 600s timeout. Both feeds run
   concurrently: events update the timeline, log lines append to `RichLog`.
   Stream termination states (complete / error-guard / timeout) must be
   rendered explicitly — never leave a silent dead pane.

2. **Server-side instance logs (Logs view / Inspect jump-off).** Add a
   polling tail primitive to `SSMService`:
   `tail_file(instance_id, path, poll_interval=2.0)` — send
   `tail -c +<offset> <path>` (byte-offset resume, not line dedup), yield new
   chunks, stop on worker cancel. Expose the known log catalog (userdata,
   model-preload, EFS mount) as named targets so the TUI shows a picker, not a
   free-text path prompt.

3. **Docker logs (Logs view).** Extend `SSMService` with
   `follow_container_logs(instance_id, service, poll_interval=3.0)`: poll
   `docker logs --since <last-poll-ts> <container>` per interval and de-dupe on
   timestamp boundary. CLI parity shipped: `geusemaker logs --follow --service
   <name>` streams container logs. PostgreSQL has no HTTP surface, so its
   container log is the primary live signal for that service.

**Worker rules (all streams):**

- Blocking SSM/boto3 generators run in `@work(thread=True, exclusive=True)`
  workers; UI mutations only via `call_from_thread` (append to `RichLog`).
- One active stream worker per pane; switching mode/stack cancels the worker
  (generator `close()`), never orphans it.
- Streaming panes set `auto_scroll=True` and `max_lines` (bounded memory);
  static panes (banner art, inventories) keep `auto_scroll=False`.
- Surface readiness delays in the UI: SSM agent wait (≤60s) renders as a
  `[WAIT] SSM AGENT…` line, not a frozen screen.
- IAM prerequisite: instance role must include `AmazonSSMManagedInstanceCore`;
  a denied SSM call renders as an actionable error line in the pane.
- Inspect stays disk-only (StateManager). Streaming is reached *from* Inspect
  via explicit jump-off keys (`l` logs, `m` monitor) — honoring
  "read-only views do not contact AWS until requested."

---

## 9. Phased rollout

Phases 0–5 are implemented — see the Phase 5 delivery log below. Remaining work
is the §7 wizard polish checklist. Changes must preserve existing service
boundaries and remain testable without making Textual mandatory.

### Phase 0 — Dependencies & design tokens (0.5–1 day)

- Bump `rich` floor to `>=14.2,<16`
- Add optional `[tui]` extra (`textual>=8.2,<9`)
- Expand `ColorTheme` + document palette in this file
- Smoke: existing CLI tests still green without Textual installed

**Exit:** `pip install -e ".[dev]"` works; importing `textual` only under `[tui]`.

### Phase 1 — Wizard brutalist polish + stage glyphs (3–5 days)

- Rich Theme wiring on shared console
- Dialog/step chrome + questionary style
- `STAGE_GLYPHS` + `print_stage()` behind verbosity guards
- Wire first stages through interactive deploy path (validate, efs, ec2, finalize)
- Snapshot/unit tests for glyph rendering helpers

**Exit:** Interactive deploy shows trademark banner + per-stage marks; CI non-interactive unchanged.

### Phase 2 — ProgressEvent contract (2–3 days)

- Introduce `ProgressEvent` + callback on `DeploymentRunner` (implemented)
- Propagate the callback through tier orchestrators for granular resource stages
- Migrate wizard progress off ad-hoc console prints where practical
- Recording tests for stage order (Tier 1 minimum)

**Exit:** Wizard deployment milestones consume events; orchestrator tests assert
the complete tier-specific sequence without Rich. **Met (2026-07-16).**

### Phase 3 — Textual shell MVP (5–8 days)

- `geusemaker/cli/tui/` package: app and TCSS foundation implemented; operational
  screens and adapters pending
- Commands: `geusemaker tui`, `deploy --tui`, `monitor start STACK --tui`
- Monitor + Status screens first (read-mostly)
- Splash uses the `MAIN_BANNER` trademark; the future timeline shows stage
  glyphs as labels

**Current state:** Opt-in shell runs on a TTY, the missing extra prints an install
hint, and service/orchestration layers do not import Textual. Monitor, Inspect,
and Deploy are operationally complete; a dedicated Status view was folded into Inspect.

### Phase 4 — Deploy-in-TUI + hardening (3–5 days)

- Extract `DeploymentDraft` / `ConfigBuilder` and YAML import/export
- Deploy screen driven by `ProgressEvent`
- Feature flag / `GEUSEMAKER_UI` for supported commands (routing implemented)
- Docs: README + architecture tech-stack update
- Manual checklist: dumb terminal, `NO_COLOR`, JSON deploy, Ctrl+C cleanup

**Exit:** Default remains the wizard; TUI deployment produces the same validated
`DeploymentConfig` and invokes the same `DeploymentRunner`. **Met (2026-07-17).**

### Phase 5 — Live streams wiring (contract in §8.4) (4–6 days)

Order of delivery (read-only first, service additions last):

0. **Configuration seam** — DONE (2026-07-17): `cli/configuration/` package
   (DeploymentDraft + ConfigBuilder), wizard `_build_config` and YAML export
   delegate to it, 64 tests incl. wizard-parity and YAML round-trip; fixed the
   nine-field silent-drop bug in the wizard path.
1. **Inspect (disk-only)** — DONE (2026-07-16): `tui/inspect_screen.py`,
   StateManager-backed picker + inventory pane, explicit empty state,
   `l`/`m` jump-off messages handled by the app. No AWS calls. 9 pilot tests.
2. **Monitor** — DONE (2026-07-16, health portion): `tui/monitor_screen.py`,
   async polling worker over the health-check client with DI seam, WAIT/ERROR
   explicit states, cancellation-on-dismiss verified. 6 pilot tests +
   6 app-integration pilot tests. Userdata tail attaches in step 3/4.
3. **Deploy** — DONE (2026-07-17): `tui/deploy_screen.py` (ConfigBuilder-driven
   form — reflective widgets, live visibility, validation pane, YAML
   import/export, LaunchRequested message) + `tui/deploy_run_screen.py`
   (ProgressEvent glyph timeline PENDING/ACTIVE/DONE/ERROR with resource IDs,
   event log, userdata stream attach at the `userdata` stage via DI seam,
   explicit success/failure terminal states, double-escape guard while
   running). `deploy --tui` now lands on the operational form. 17 screen pilot
   tests + 2 app-integration tests. Orchestrator ProgressEvent propagation was
   DONE 2026-07-16.
4. **Logs view** — DONE (2026-07-17): `SSMService.tail_file()` (byte-offset
   resume) and `SSMService.follow_container_logs()` (docker `--since` polling
   with timestamp de-dupe; container mapping single-sourced in ssm.py) +
   `tui/logs_screen.py` (grouped INSTANCE/CONTAINERS target picker, WAIT/
   ENDED/DETACHED/ERROR explicit states, per-attach cancellation tokens),
   reached from Inspect via `l`. CLI parity shipped:
   `logs --follow --service <name>` now streams containers. 18 service tests +
   8 screen pilot tests + integration test.

**Phase 5 exit criteria met (2026-07-17):** no placeholder summaries remain —
every mode renders real data or an explicit empty/error state; worker
cancellation is pilot-tested (mode switch mid-stream, dismiss mid-stream,
double-escape during deploy); the suite passes without `[tui]` installed
(importorskip-guarded).

Implementation note: `$gm-*` variables from `brutalist.tcss` are NOT visible in
widget/screen `DEFAULT_CSS` (Textual 8.2.8 scopes variables per stylesheet
source — `UnresolvedVariableError`). Cleanup done 2026-07-17: `tui/theme.py`
owns `GM_TOKENS`/`GM_VARIABLES_TCSS`; every screen prepends the shared block to
its `DEFAULT_CSS`, and `test_theme.py` asserts brutalist.tcss stays in sync
and no screen restates values.

**Exit:** No placeholder summaries remain; every pane either renders real data
or an explicit empty/error state. Worker cancellation verified with pilot
tests (switch mode mid-stream; quit mid-stream). Suite passes without `[tui]`.

---

## 10. File / package map

```
geusemaker/cli/
├── branding.py              # MAIN/DEPLOY banners + STAGE_GLYPHS (extend)
├── components/
│   ├── theme.py             # brutalist ColorTheme + Rich Theme factory
│   ├── dialogs.py           # wizard prompts (polish)
│   └── stage.py             # print_stage helper (new)
├── interactive/             # wizard adapter, prompt navigation, resume behavior
├── configuration/           # DeploymentDraft + ConfigBuilder + YAML round-trip (Phase 5.0)
├── tui/                     # optional import (requires [tui] extra)
│   ├── app.py               # Hub, mode routing, screen push/pop, jump-off handlers
│   ├── splash.py            # Animated boot splash (MAIN_BANNER reveal, skip on key)
│   ├── inspect_screen.py    # Disk-only stack picker + inventory (Phase 5.1)
│   ├── monitor_screen.py    # Health polling worker + event log (Phase 5.2)
│   ├── deploy_screen.py     # ConfigBuilder-driven deploy form (Phase 5.3)
│   ├── deploy_run_screen.py # ProgressEvent timeline + userdata stream (Phase 5.3)
│   ├── logs_screen.py       # Instance/container log stream picker (Phase 5.4)
│   ├── theme.py             # GM_TOKENS / GM_VARIABLES_TCSS shared palette (from ColorTheme)
│   └── brutalist.tcss       # Shared Textual presentation ($gm-* tokens)
└── progress_events.py       # shared UI-neutral progress contract
```

---

## 11. Testing strategy

| Layer | Approach |
|-------|----------|
| Stage glyphs | Pure functions → string snapshots |
| Shared configuration | Wizard and Textual adapters build identical `DeploymentConfig` fixtures |
| ProgressEvent | Recording callback in runner and tier-orchestrator tests (moto/stubs) |
| Dialogs | Existing `scripted_inputs` / non-TTY fallbacks |
| Textual | Optional: `textual` pilot/`App.run_test()` behind `[tui]` marker; skip if extra missing |
| Regression | Full `./scripts/test.sh` without Textual installed must pass |

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Rich 15 + Textual 8 widen transitive graph | Optional `[tui]`; pin `<9` / `<16` |
| Stage glyphs noisy in CI logs | Gate on TTY + verbosity; never in machine output |
| Orchestrator spam `console.print` | Phase 2 event bus; deprecate direct prints gradually |
| Brutalist low-contrast temptation | Stick to palette table; review in light & dark terminals |
| Dual UX drift | Shared tokens + ProgressEvent; one branding module |

---

## 13. Done criteria

- [x] Trademark banners retained; compact mark used in the TUI shell
- [x] Compact stage ASCII marks available for wizard progress events
- [x] Brutalist theme applied to Rich and Textual shells
- [x] Base install remains wizard-only; `[tui]` enables the full-screen app
- [x] Services/orchestration remain free of Textual/questionary imports
- [x] Non-interactive JSON/YAML paths retain their one-document stdout contract
- [x] Routing for `geusemaker tui`, `deploy --tui`, `monitor start --tui`, and command-scoped `GEUSEMAKER_UI=tui`
- [x] Extract a UI-neutral `DeploymentDraft` / `ConfigBuilder` shared by wizard and Textual forms
- [x] Add wizard YAML export and TUI YAML import through the shared configuration layer
- [x] Propagate `ProgressEvent` callbacks through tier orchestrators (granular stages + error events, per-tier recording tests)
- [x] Replace placeholder mode summaries with AWS-backed worker-driven live screens
- [x] Deploy screen streams ProgressEvent timeline + userdata log concurrently (§8.4.1)
- [x] Instance log tailing via `SSMService.tail_file()` with named log catalog (§8.4.2)
- [x] Docker log following via `SSMService.follow_container_logs()` + CLI `--follow` parity (§8.4.3)
- [x] Add optional Textual pilot tests when the `[tui]` extra is installed (54 tests under tests/unit/test_cli/test_tui/, `pytest.importorskip` guarded)

---

## 14. References

- Textual latest: [PyPI textual 8.2.8](https://pypi.org/project/textual/), [textual.textualize.io](https://textual.textualize.io/)
- Rich latest: [PyPI / GitHub rich 15.0.0](https://github.com/Textualize/rich)
- Layout: [Design a Layout](https://textual.textualize.io/how-to/design-a-layout/)
- Design systems: [Monospace Design TUI](https://github.com/coreyt/monospace-design-tui), 2026 brutalist UI field guides
- Internal: `geusemaker/cli/branding.py`, Epic 8 stories (`docs/stories/8.*.md`), `docs/architecture/3-tech-stack.md` (update when implementing)

---

## 15. Suggested next implementation PRs

1. Extract `DeploymentDraft` / `ConfigBuilder` from `InteractiveFlow`; add shared
   conditional-validation fixtures and YAML round-trip tests.
2. Propagate `ProgressEvent` callbacks through Tier 1/2/3 and assert complete,
   tier-specific event sequences without Rich or Textual.
3. Implement the disk-only Inspect screen and optional Textual pilot tests.
4. Implement the Monitor worker and cancellation contract.
5. Build the Textual deploy form on the shared configuration layer, then connect
   it to `DeploymentRunner` and concurrent userdata streaming.
