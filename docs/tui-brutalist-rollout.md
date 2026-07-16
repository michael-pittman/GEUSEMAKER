# GeuseMaker TUI Rollout — Brutalist Hybrid UI

**Status:** Implemented foundation with follow-up live-screen work

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
| **Full TUI** | Opt-in | Textual 8.x | Multi-pane status, live deploy, monitor hub |

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
  InteractiveFlow / ConfigBuilder
  DeploymentRunner + ProgressEvent
  Tier*Orchestrator, services, StateManager
```

### Entry points

```bash
geusemaker deploy                 # wizard (default)
geusemaker deploy --tui           # full-screen deploy (requires [tui])
geusemaker tui                    # hub: deploy / monitor / status / logs
geusemaker monitor --tui          # multi-pane live monitor
GEUSEMAKER_UI=tui geusemaker …    # env override when TTY
```

If `[tui]` missing: clear error → `pip install 'geusemaker[tui]'`.

---

## 6. Shared progress contract (critical seam)

Extract before building Textual (Phase 2). Both shells consume the same events.

```python
# planned: geusemaker/cli/progress_events.py (or models/)
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

- `DeploymentRunner` / orchestrator hooks call `on_progress(ProgressEvent)`.
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

- [ ] Step chrome: `STEP 03/11 · INSTANCE` uppercase, muted help under prompt
- [ ] Shared questionary `Style` mapped from brutalist tokens (hex only)
- [ ] Searchable / scrollable selects for long VPC/subnet/AMI lists
- [ ] Consistent Esc/back/quit via `DialogBack` / `DialogAbort`
- [ ] Pre-launch review panel with hard borders (no soft cards)
- [ ] Stage glyphs on validate → finalize
- [ ] Fold remaining `click.prompt` / `click.confirm` in destroy/rollback into `Dialogs`
- [ ] Resume menu: resume / restart / export YAML

Wizard stays linear and scrollback-friendly — **do not** embed the wizard inside Textual unless a later epic explicitly merges them.

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
│ [Logs]       │                                          │
├──────────────┴──────────────────────────────────────────┤
│ FOOTER  key bindings  │  spot/on-demand  │  last event  │  dock bottom
└─────────────────────────────────────────────────────────┘
```

### 8.2 Screens (priority order)

1. **Monitor** — health table + log pane (port existing Rich Live from `monitor.py` / userdata stream)
2. **Status / Inspect** — resource inventory
3. **Deploy** — checklist driven by `ProgressEvent`; config from wizard export or in-TUI form
4. **Hub** — `geusemaker tui` landing

### 8.3 Textual implementation notes

- `App` + `Screen` per mode; `CSS_PATH = "brutalist.tcss"`
- `border: heavy` / `tall`; background `$surface`; accent `$signal`
- AWS calls in workers; UI thread only applies events
- Bindings: `q` quit, `?` help, `tab` focus cycle, `d` deploy, `m` monitor
- Do not redraw whole screen on each SSM line — append to `RichLog`

---

## 9. Phased rollout

Phases 0–3 and the Phase 4 command/environment integration are implemented. The
remaining work is replacing the current deploy/monitor/inspect workspace summaries
with AWS-backed Textual workers and richer live widgets. That work must preserve the
existing service boundaries and must be tested without making Textual mandatory.

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

- Introduce `ProgressEvent` + callback on `DeploymentRunner` / tier orchestrators
- Migrate wizard progress off ad-hoc console prints where practical
- Recording tests for stage order (Tier 1 minimum)

**Exit:** Wizard consumes events only; orchestrator tests assert sequence without Rich.

### Phase 3 — Textual shell MVP (5–8 days)

- `geusemaker/cli/tui/` package: app, screens, TCSS, adapters
- Commands: `geusemaker tui`, `deploy --tui`, `monitor --tui`
- Monitor + Status screens first (read-mostly)
- Header uses `MAIN_BANNER` trademark; timeline shows stage glyphs as labels

**Exit:** Opt-in TUI runs on TTY; missing extra prints install hint; no service-layer Textual imports.

### Phase 4 — Deploy-in-TUI + hardening (3–5 days)

- Deploy screen driven by ProgressEvent
- Feature flag / `GEUSEMAKER_UI`
- Docs: README + architecture tech-stack update
- Manual checklist: dumb terminal, `NO_COLOR`, JSON deploy, Ctrl+C cleanup

**Exit:** Default remains wizard; TUI is documented optional experience.

---

## 10. File / package map

```
geusemaker/cli/
├── branding.py              # MAIN/DEPLOY banners + STAGE_GLYPHS (extend)
├── components/
│   ├── theme.py             # brutalist ColorTheme + Rich Theme factory
│   ├── dialogs.py           # wizard prompts (polish)
│   └── stage.py             # print_stage helper (new)
├── interactive/             # wizard flow (keep)
├── tui/                     # NEW (optional import)
│   ├── app.py
│   ├── brutalist.tcss
│   ├── app.py               # Current hub and mode workspaces
│   └── brutalist.tcss       # Shared Textual presentation
└── progress_events.py       # NEW shared contract
```

---

## 11. Testing strategy

| Layer | Approach |
|-------|----------|
| Stage glyphs | Pure functions → string snapshots |
| ProgressEvent | Recording callback in unit tests (moto/stubs) |
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
- [x] `geusemaker tui`, `deploy --tui`, `monitor start --tui`, and `GEUSEMAKER_UI=tui`
- [ ] Replace placeholder mode summaries with AWS-backed worker-driven live screens
- [ ] Add optional Textual pilot tests when the `[tui]` extra is installed

---

## 14. References

- Textual latest: [PyPI textual 8.2.8](https://pypi.org/project/textual/), [textual.textualize.io](https://textual.textualize.io/)
- Rich latest: [PyPI / GitHub rich 15.0.0](https://github.com/Textualize/rich)
- Layout: [Design a Layout](https://textual.textualize.io/how-to/design-a-layout/)
- Design systems: [Monospace Design TUI](https://github.com/coreyt/monospace-design-tui), 2026 brutalist UI field guides
- Internal: `geusemaker/cli/branding.py`, Epic 8 stories (`docs/stories/8.*.md`), `docs/architecture/3-tech-stack.md` (update when implementing)

---

## 15. Suggested first implementation PR

1. Phase 0 dependency bumps + `[tui]` extra (no behavior change).  
2. Phase 1 branding: palette + `STAGE_GLYPHS` + wire 3–4 stages in interactive deploy.  
3. Follow-up PR: ProgressEvent extraction.  
4. Follow-up PR: Textual Monitor MVP.
