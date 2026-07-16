# Deployment shape and instance recommendations

GeuseMaker treats deployment topology and compute workload as separate decisions:

- `tier` remains the backward-compatible persisted topology identifier: `dev`,
  `automation`, or `gpu`. These map to development, production, and global
  topology respectively.
- `workload` selects `cpu` or `gpu` compute independently. If it is absent in an
  older configuration, the legacy `gpu` tier implies a GPU workload and other
  tiers imply CPU.

Instance recommendations evaluate every eligible candidate instead of accepting
the first available item. `instance_preference` controls ranking:

- `balanced`: honors the requested purchase mode and balances price with the
  spot placement score.
- `lowest_cost`: chooses the least expensive eligible candidate.
- `highest_availability`: prioritizes the requested purchase mode and the best
  placement score.
- `performance`: favors the highest-capability candidate in the supported list.

The recommendation result includes up to three ranked alternatives with price,
purchase mode, and placement score. A manual instance choice remains a UI concern
and bypasses automatic recommendation.

No policy promises AWS capacity. Placement scores and prices are observations at
recommendation time, so deployment validation must still run before provisioning.
