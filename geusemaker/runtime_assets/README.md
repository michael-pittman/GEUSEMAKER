# GeuseMaker Runtime Assets

This directory is packaged with the GeuseMaker CLI to accelerate EC2 initialization. The UserData generator can embed these assets directly (with `use_runtime_bundle=true`) so the instance can provision itself without downloading everything from the internet.

Included by default:
- `docker-compose.yml`: The service stack definition used by UserData.
- `runtime.env.example`: Example runtime env file used by the bundled compose.
- `bin/`, `efs-utils/`, `images/`: Drop optional binaries or pre-baked Docker images here before building a bundle.

Usage:
1. Add any optional artifacts (prebuilt `amazon-efs-utils` packages, Docker Compose plugin, preloaded image tarballs) under the directories below.
2. Run `./scripts/build_runtime_bundle.sh` to produce `runtime-bundle.tar.gz` for embedding.
3. Deploy with `--use-runtime-bundle` (or set `use_runtime_bundle: true` in config) so the UserData script unpacks this bundle on the instance.
