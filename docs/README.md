# GeuseMaker documentation

This directory is the documentation entry point for GeuseMaker. The code and
CLI help are authoritative when a historical planning document disagrees with
the current implementation.

## Start here

- [Project README](../README.md) — installation, first deployment, and common commands.
- [Product requirements](prd/index.md) — canonical, sectioned PRD.
- [Architecture](architecture/index.md) — canonical, sectioned architecture reference.
- [Instance recommendations](instance-recommendation.md) — topology, workload, and ranking policies.
- [TUI rollout](tui-brutalist-rollout.md) — implemented shell and remaining rollout work.

## Delivery records

- [Epics and stories summary](EPICS_AND_STORIES_SUMMARY.md)
- [Epics](epics/) — feature-level delivery records.
- [Stories](stories/) — detailed acceptance criteria and implementation notes.
- [Analysis](analysis/) — focused technical reviews.

These records describe decisions at the time they were written. Their status
labels are historical unless the summary explicitly says otherwise.

## Operations

- [Runtime assets](../geusemaker/runtime_assets/README.md)
- [Maintenance scripts](../scripts/README.md)
- [n8n workflows](../Workflows/README.md)
- [Sample configuration](../config/README.md)
- [Stack-specific spot automation design](spot-instance-automation-nga.md)

## Historical snapshots

- [Monolithic PRD snapshot](PRD.md) — retained for traceability; use `prd/index.md` for edits.
- [Monolithic architecture snapshot](architecture.md) — retained for traceability; use `architecture/index.md` for edits.
- [2025 codebase review](CODEBASE_REVIEW.md) — findings from an earlier implementation state.

## Documentation conventions

1. Update the sectioned PRD and architecture documents, not their monolithic snapshots.
2. Use repository-relative links and exact CLI command names.
3. Mark documents as `Current`, `Historical`, `Design`, or `Implemented with follow-up work`.
4. Keep workload (`cpu`/`gpu`) separate from topology tier (`dev`/`automation`/`gpu`).
5. Never include credentials, private keys, secrets, or live customer data.
