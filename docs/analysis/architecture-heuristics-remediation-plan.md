# Architecture Heuristics Remediation Plan

**Status:** Delivered (Phases 1–5 landed 2026-07-17) — see Definition of Done  
**Date:** 2026-07-17  
**Source:** Architecture heuristics review (layering, service patterns, state, orchestration tiers)  
**Verdict driving this plan:** Significant drift from documented `CLI → Orchestration → Services → Infrastructure` boundaries

This plan turns every finding from the review into sequenced implementation work. Code and CLI help remain authoritative if this plan disagrees with a later change; update this document when a phase lands.

## Goals

1. Restore import direction: presentation depends on workflows; workflows never depend on presentation.
2. Finish the topology (`tier`) vs compute (`workload`) split through UserData/runtime.
3. Keep AWS/business workflow logic out of the CLI runner.
4. Shrink god-class orchestrators without a cosmetic-only package reshuffle.
5. Align docs and coding-rule exceptions with reality (state paths, bare `Exception`, ownership).

## Non-goals

- Rewriting the tier inheritance hierarchy (`Tier3 → Tier2 → Tier1` stays).
- Moving update/rollback packages solely for aesthetics (stabilize ownership docs first; optional later).
- Changing the public Click/TUI command surface unless a phase requires a thin adapter change.
- Force-migrating every best-effort destroy catch to typed exceptions in one PR (phased tightening).

## Current vs target

```text
Today (drift)                         Target
─────────────                         ──────
CLI ⇄ Orchestration (soft cycle)      CLI → Orchestration → Services → Infra
Orchestration → cli.console/EMOJI     Orchestration → progress contract only
Services/compute → cli.console        Services → logging / progress events only
progress_events under cli/            progress contract under shared package
UserData GPU gated on tier=="gpu"     GPU gated on effective_workload
ACM/cert flow in DeploymentRunner     ACM/cert flow in orchestration/services
```

## Finding → work map

| ID | Severity | Finding | Phase |
|---|---|---|---|
| C1 | Critical | Orchestration imports CLI (`console`/`EMOJI`) | 1 |
| C2 | Critical | Compute services import CLI presentation | 1 |
| H4 | High | Dual progress channels; contract lives under `cli/` | 1 |
| H1 | High | Workload vs tier still coupled in UserData | 2 |
| H2 | High | ACM / tier coercion / workflow logic in CLI runner | 3 |
| H3 | High | God-class Tier1 (~1080 LOC) | 4 |
| M1 | Medium | Non-BaseService facades inconsistent (document + light align) | 5 |
| M2 | Medium | Bare `Exception` on critical paths | 5 |
| M3 | Medium | State path doc drift (`deployments/` vs flat) | 5 |
| M4 | Medium | Raw dicts in snapshots / intermediate DTOs | 5 (partial) / backlog |
| M5 | Medium | Update/rollback “orchestrators” under `services/` | 5 (docs) / backlog |
| M6 | Medium | Ad-hoc `~/.geusemaker` I/O for monitor PIDs/logs | 5 (document as intentional) |
| L4 | Low | High-level diagram places UserData under Infra | 5 |

Healthy areas (do not regress): tier inheritance shape, BaseService for boto3 managers, StateManager for deployment state, models as shared contracts, no secrets in deployment state, host-side `print()` discipline.

---

## Phase 1 — Invert presentation dependencies

**Addresses:** C1, C2, H4  
**Risk:** Medium (touches deploy UX for CLI and TUI)  
**Suggested PR size:** One focused PR; do not mix with UserData/workload changes

### Intent

Orchestration and services emit progress/log events only. CLI and TUI render them. Remove the soft import cycle.

### Work items

1. **Move the progress contract out of `cli/`**
   - Relocate `geusemaker/cli/progress_events.py` to a presentation-free package, e.g. `geusemaker/progress/` (or `geusemaker/models/progress.py` if keeping surface small).
   - Re-export a thin compatibility shim from `cli/progress_events.py` if needed for one release, then delete the shim.
   - Ensure the new module imports neither Rich, Click, Textual, nor `geusemaker.cli`.

2. **Strip CLI imports from orchestration**
   - Remove `from geusemaker.cli import console` / `EMOJI` / branding from `orchestration/tier1.py`, `tier2.py`, `tier3.py`.
   - Replace every `console.print(...)` with `_emit_progress(...)` (or structured logging for non-progress diagnostics).
   - Keep stage semantics: validate, vpc, efs, iam, ec2, alb, cloudfront, health, cost — same event names the TUI already consumes where applicable.

3. **Strip CLI imports from compute services**
   - `services/compute/spot.py` and `services/compute/selector.py`: remove console/branding imports.
   - Return structured results (existing recommendation models) and optional progress callbacks; let CLI display formatters render.

4. **Audit remaining `services → cli` edges**
   - Confirm AST/import graph: `orchestration` and `services` must not import `geusemaker.cli`.
   - `services/monitoring/notifiers.py` Rich usage: either move panel construction to `cli/display/` or accept a documented Rich dependency for notifiers only (prefer moving presentation out).

5. **Wire CLI/TUI adapters**
   - `DeploymentRunner`, Click deploy path, and TUI Deploy screen subscribe to `ProgressCallback` / event stream and map events to Rich/Textual widgets.
   - Machine-readable (`--output json`) paths must keep working without requiring the `[tui]` extra.

### Acceptance criteria

- [ ] `python -c` / import-linter or a small test asserts `orchestration` and `services` do not import `geusemaker.cli` (allowlist empty or explicit).
- [ ] Deploy via CLI and TUI still shows stage progress and success/failure messaging.
- [ ] Unit tests for progress event emission cover Tier1 happy-path stage sequence (stub services).
- [ ] No new `console.print` in `orchestration/` or `services/compute/`.

### Test plan

- Unit: orchestrator emits expected `ProgressEvent` sequence with stubbed AWS services.
- Unit: compute selector returns recommendations without importing cli.
- Manual: `geusemaker deploy --tui` and non-TUI wizard through validate → resource stages (dry or mocked if available).
- Regression: `./scripts/lint.sh` and targeted orchestration/compute tests.

---

## Phase 2 — Finish workload / topology split in runtime

**Addresses:** H1  
**Risk:** High (changes EC2 bootstrap behavior)  
**Depends on:** Prefer after Phase 1 to avoid mixing UX and bootstrap diffs; can run in parallel if staffing allows  
**Suggested PR size:** One PR with explicit migration notes

### Intent

Topology (`tier`: `dev` / `automation` / `gpu`) controls networking/CDN shape. Workload (`cpu` / `gpu`) controls NVIDIA runtime, GPU Docker images, and model preload. Legacy configs without `workload` keep inferring GPU only when `tier == "gpu"`.

### Work items

1. **Extend `UserDataConfig`**
   - Add `workload: Literal["cpu", "gpu"]` (or pass `effective_workload` from `DeploymentConfig`).
   - Orchestrators pass `workload=config.effective_workload` (or equivalent) when building UserData — not tier alone for GPU features.

2. **Rewrite template gates**
   - Replace `{% if tier == "gpu" %}` NVIDIA/GPU blocks with workload checks in:
     - `gpu.sh.j2`
     - `docker.sh.j2` (GPU runtime / nvidia toolkit)
     - `services.sh.j2` (image/tag selection)
     - `ollama-models.sh.j2` (preload behavior)
   - Keep **topology-only** gates on tier/flags: self-signed HTTPS (dev), ALB metrics (automation+), CloudFront (tier3), spot interruption protection where tied to topology docs.

3. **Align cost / estimator / recommendation docs**
   - Ensure cost assembly and instance recommendation paths already using `workload` stay consistent with UserData.
   - Update `docs/instance-recommendation.md` and architecture notes if any still imply “GPU tier == GPU workload.”

4. **Compatibility matrix (document in PR + tests)**

   | tier | workload | Expected runtime |
   |---|---|---|
   | dev | cpu | No NVIDIA; CPU images |
   | dev | gpu | NVIDIA + GPU images on single-instance topology |
   | automation | cpu | ALB topology, CPU runtime |
   | automation | gpu | ALB topology, NVIDIA runtime |
   | gpu | cpu | CloudFront topology, CPU runtime (no NVIDIA) |
   | gpu | gpu | CloudFront topology, NVIDIA runtime |
   | legacy (no workload) | — | Infer `gpu` workload iff `tier == "gpu"` |

### Acceptance criteria

- [ ] Rendering UserData for `tier=dev, workload=gpu` includes NVIDIA/GPU sections.
- [ ] Rendering UserData for `tier=gpu, workload=cpu` excludes NVIDIA/GPU sections.
- [ ] Legacy config without `workload` and `tier=gpu` still gets GPU UserData.
- [ ] Template unit tests cover the six explicit matrix cells above (string/fixture asserts).

### Test plan

- Unit: `UserDataGenerator` fixtures per matrix cell.
- Unit: `DeploymentConfig.effective_workload` legacy inference.
- Manual smoke (optional): one CPU and one GPU deploy on cheap/dev topology if environment available.

---

## Phase 3 — Pull workflow logic out of `DeploymentRunner`

**Addresses:** H2  
**Risk:** Medium  
**Depends on:** Phase 1 recommended (cleaner callbacks while moving ACM progress)  
**Suggested PR size:** One PR; avoid splitting ACM mid-flight across branches

### Intent

CLI builds config and renders. Orchestration (or a dedicated service) owns ACM DNS validation, tier→feature normalization, and orchestrator selection inputs.

### Work items

1. **Extract ACM / Route53 certificate provisioning**
   - Move the multi-step ACM request + DNS validation loop from `cli/interactive/runner.py` into orchestration (preferred: Tier2/Tier3 pre-step) or `services/acm` + a small orchestration helper.
   - Emit progress events for “requesting cert”, “waiting for DNS validation”, “issued”.

2. **Centralize tier → feature normalization**
   - Move flag coercion (`enable_alb`, HTTPS, CloudFront-related defaults) next to orchestrator selection or into `DeploymentConfig` validators / a pure `normalize_deployment_config(config) -> DeploymentConfig` in `models/` or `orchestration/`.
   - CLI may call the pure normalizer; it must not own AWS side effects.

3. **Thin `DeploymentRunner`**
   - Target shape: load/validate config → normalize → optional preflight (budget/validation services) → `orchestrator.deploy(config, progress=...)` → render result.
   - Keep orchestrator factory in CLI **or** move to `orchestration/factory.py` if that clarifies ownership; either is fine if AWS work is out of CLI.

### Acceptance criteria

- [ ] `cli/interactive/runner.py` has no direct ACM/Route53 provisioning loop.
- [ ] Tier2/Tier3 deploys with custom domain still obtain certificates.
- [ ] Unit tests cover cert helper with moto stubs (or existing ACM service tests extended).
- [ ] Failure messages for cert timeout remain actionable in CLI output via progress/error events.

### Test plan

- Unit: ACM helper happy path + timeout.
- Unit: normalize_deployment_config for each tier.
- Manual: automation-tier deploy with domain (if credentials/domain available).

---

## Phase 4 — Decompose Tier1 without breaking inheritance

**Addresses:** H3  
**Risk:** Medium–High  
**Depends on:** Phase 1 (presentation already out makes extraction safer)  
**Suggested PR size:** 2–3 PRs (extract stages incrementally)

### Intent

Keep `Tier3Orchestrator → Tier2Orchestrator → Tier1Orchestrator`. Reduce Tier1 blob size by extracting stage collaborators, not by inventing a new framework.

### Work items

1. **Identify stage modules** (suggested split under `orchestration/stages/` or private helpers on Tier1):
   - Networking (VPC/SG attach)
   - EFS + mount targets
   - IAM instance profile
   - UserData assembly
   - EC2 launch + IAM propagation retry
   - Post-launch (spot automation hooks, HTTPS SG rules, cost assembly)
2. **Extract one stage per PR** with identical call order and state save points (especially partial state after EFS/IAM before EC2).
3. **Preserve rollback hooks** and partial-state saves documented in CLAUDE.md / architecture workflows.
4. **Do not** move AWS API calls into CLI while refactoring.

### Acceptance criteria

- [ ] `tier1.py` LOC materially reduced (target: &lt; ~600 for the coordinator; stages hold the rest).
- [ ] Existing orchestration unit tests (stub services) still pass without behavior change.
- [ ] Partial-state save points remain after EFS/IAM before EC2 launch.

### Test plan

- Full orchestration stub suite after each extraction PR.
- Diff review focused on call order and state mutations only.

---

## Phase 5 — Hygiene: docs, exceptions, ownership clarity

**Addresses:** M1–M6, L4  
**Risk:** Low  
**Can run anytime** (preferably after or interleaved with Phases 1–2 for accurate docs)

### Work items

1. **State path docs (M3)** — ✅ Landed 2026-07-17
   - Align `CLAUDE.md`, `docs/architecture/4-data-models.md`, and any other flat-path mentions with `StateManager`’s `~/.geusemaker/deployments/{stack}.json`.
   - Result: verified against `infra/state.py` — real path is nested `~/.geusemaker/deployments/<stack_name>.json`. Corrected `CLAUDE.md`, `docs/architecture/4-data-models.md`, and the historical `docs/architecture.md` flat-path mention; tightened the diagram label in `docs/architecture/2-high-level-architecture.md`. `docs/architecture/8-database-schema-json-state-files.md` was already correct.

2. **Bare `Exception` policy (M2)** — docs part (Rule #3 wording) ✅ Landed 2026-07-17; code tightening owned by the code agent
   - Document intentional best-effort cleanup catches (destruction/IAM teardown) as an approved exception with `# noqa: BLE001` and a one-line comment citing “best-effort cleanup.”
   - Tighten non-cleanup paths in orchestration (timeouts/rollback) to specific exception types where cheap.
   - Reworded `CLAUDE.md` rule 3 to the real policy (specific-by-default; blind `except Exception` allowed only in cleanup/rollback/monitoring with `# noqa: BLE001` + reason).

3. **BaseService consistency (M1)** — ✅ Landed 2026-07-17
   - Document which types are *facades* (Destruction, Update, Rollback, Cost, Backup, HealthMonitor, UserDataGenerator) and are not required to subclass `BaseService`.
   - No mass inheritance change required unless a facade starts owning a raw boto3 client.
   - Documented in `docs/architecture/12-coding-standards.md` §12.4 (verified each facade does not subclass `BaseService`).

4. **Ownership of update/rollback (M5)** — ✅ Landed 2026-07-17
   - Architecture/source-tree note: “workflow coordinators for update/rollback live under `services/{update,rollback}/` by historical placement; new multi-resource deploy workflows belong in `orchestration/`.”
   - Optional backlog: relocate only if a later epic needs it.
   - Added to `docs/architecture/9-source-tree.md` §9.1.

5. **Monitor PID / log paths (M6)** — ✅ Landed 2026-07-17
   - Document as intentional non-StateManager persistence under `~/.geusemaker/monitoring` and logs.
   - Documented in `docs/architecture/8-database-schema-json-state-files.md` §8.1 (verified against `cli/commands/monitor.py`).

6. **Diagram correction (L4)** — ✅ Landed 2026-07-17
   - Move UserData from “Infrastructure” to “Service Layer” in `docs/architecture/2-high-level-architecture.md`.

7. **Raw dict snapshots (M4) — partial**
   - Short term: leave `last_healthy_state` / `previous_states` as `dict[str, Any]` but document why (versioned blobs).
   - Backlog: typed snapshot models when update/rollback epics touch that surface.

### Acceptance criteria

- [x] No remaining documented flat state path that contradicts `infra/state.py`. (2026-07-17)
- [x] Architecture diagram places UserData under services. (2026-07-17)
- [x] Facade vs BaseService distinction is written in coding standards or source-tree ownership. (2026-07-17)

---

## Backlog

**Landed 2026-07-17 (follow-up pass):**

| Item | Outcome |
|---|---|
| Tier2/Tier3 stage decomposition (extends Phase 4) | ✅ Done — ALB → `orchestration/stages/alb.py`, CloudFront → `orchestration/stages/cloudfront.py`; tier2.py 574→343, tier3.py 295→156; `_deploy_impl` order + state saves + inheritance unchanged |
| Typed snapshot models for rollback blobs (M4 full) | ✅ Done — non-recursive `DeploymentSnapshot` (`models/deployment.py`) types `last_healthy_state`/`previous_states`; `extra="ignore"` preserves backward-compat with legacy full-dump state JSON (no migration needed); rollback reads it directly; regression test added |
| Physical move of `UpdateOrchestrator` / `RollbackService` into `orchestration/` | ✅ Done — `git mv` to `orchestration/update.py` + `orchestration/rollback.py`; operators (`InstanceUpdater`/`ContainerUpdater`) stay in `services/update/`; barrels, CLI importers, tests, CLAUDE.md updated; no `services → orchestration` cycle |
| Pre-existing flaky monitor TUI test | ✅ Fixed — root cause was a teardown race (polling worker queried the DOM mid-prune); `monitor_screen.py` now caches widget refs in `on_mount` and guards on `is_attached`; verified 40× + directory loops |

**Landed 2026-07-17 (second follow-up pass — backlog cleared):**

| Item | Outcome |
|---|---|
| Full BLE001 eradication in destruction | ✅ Done — all 34 blind `except Exception`/`# noqa: BLE001` in `services/destruction/service.py` narrowed to specific types (16 `AWSError`, 18 `(ClientError, BotoCoreError)`); programming bugs now propagate, AWS/cleanup failures still best-effort; no stub changes needed |
| Import-linter in CI | ✅ Done — `import-linter` dep + `[tool.importlinter]` layered contract (`cli > orchestration > services > infra`) + the two forbidden edges (3 kept / 0 broken); wired into `scripts/lint.sh`; added the repo's first CI workflow (`.github/workflows/ci.yml`) running lint + tests. Pre-existing whole-tree ruff debt in `scripts/`/`tests/` cleaned so CI is green on first run |

Nothing remains deferred.

> Local note: `venv/bin/activate` still hardcodes the pre-move path (`/Users/nucky/Repos/GEUSEMAKER`), so `scripts/lint.sh` can't find tools when run against this stale venv locally — recreate the venv (`python3.12 -m venv venv && pip install -e ".[dev,tui]"`). CI is unaffected (fresh install).

---

## Suggested delivery order

```text
Week 1     Phase 1  — progress contract + kill cli imports from orchestration/services
Week 1–2   Phase 5  — doc hygiene (can start immediately; finish after Phase 1 naming)
Week 2     Phase 2  — workload in UserData + template matrix tests
Week 3     Phase 3  — ACM/normalize out of DeploymentRunner
Week 3–4   Phase 4  — Tier1 stage extraction (incremental PRs)
Later      Backlog items with their owning epics
```

Parallelization: Phase 5 docs can start day one. Phase 2 can parallel Phase 1 only if teams avoid touching the same orchestrator print sites.

## Definition of done (whole plan)

**Landed 2026-07-17 — Phases 1–5 all complete. Full suite: 502 passed, 0 failed; ruff clean (BLE001 now active); `ruff format` clean across the package.**

- [x] Import graph: `orchestration` ↛ `cli`, `services` ↛ `cli` (AST guard test `tests/unit/test_architecture/test_import_direction.py`; zero real imports — only docstring mentions remain).
- [x] Progress events are the sole orchestration→UI channel for deploy stages (orchestration/compute `console.print` replaced by module logging; `progress_events` contract relocated to `geusemaker/progress/` with a back-compat shim in `cli/`).
- [x] UserData GPU behavior follows `effective_workload`, with legacy inference preserved (`UserDataConfig.workload` + after-validator; 7 GPU-runtime template gates flipped to `workload`, 3 topology gates kept on `tier`; 6-cell matrix tests added).
- [x] CLI runner has no ACM provisioning side effects (extracted to `orchestration/certificates.py::CertificateProvisioner`; tier→feature coercion extracted to `orchestration/normalization.py`).
- [x] Tier1 coordinator is stage-decomposed; inheritance unchanged (`tier1.py` 1047→582 LOC; logic moved to `orchestration/stages/`; `_deploy_impl` verbatim, partial-state save preserved at Step 4).
- [x] Docs match state paths (`~/.geusemaker/deployments/<stack>.json`), UserData ownership (Service layer), and facade patterns (coding-standards §12.4).
- [x] Lint + unit suites green; matrix and progress tests added (+31 tests over the 471 baseline: guard, workload matrix, certificate, normalization, stage helpers).

### Related code-heuristics findings closed alongside this plan (whole-repo scan)
- [x] CH1 — blocking boto3 call in `async` wrapped in `asyncio.to_thread` (`services/validation/postdeployment.py`).
- [x] CH4 — substring error-matching replaced by botocore error codes via new `AWSError(RuntimeError).code` (`base.py`, `iam.py`, `destruction/service.py`).
- [x] CH5 — `except Exception` around optional import narrowed to `ImportError` (`monitoring/monitor.py`).
- [x] CH2/CH3/M2 — `BLE001` removed from ruff global ignore (was making all `# noqa: BLE001` dead no-ops); rule now active and enforces annotated blind-except; CLAUDE.md Rule #3 reworded to the real policy.

## References

- Architecture ownership & import direction: [Source Tree](../architecture/9-source-tree.md)
- Layered style: [High Level Architecture](../architecture/2-high-level-architecture.md)
- Coding rules: [Coding Standards](../architecture/12-coding-standards.md), `CLAUDE.md`
- Workload vs topology: [Instance recommendations](../instance-recommendation.md)
- Related UX surface: [TUI brutalist rollout](../tui-brutalist-rollout.md)
