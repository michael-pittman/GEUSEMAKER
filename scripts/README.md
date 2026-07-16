# Maintenance scripts

Scripts are grouped by purpose even though they remain in one directory to preserve
existing operator commands and references.

## Development

- `test.sh` — run the test suite.
- `lint.sh` — run formatting, linting, and type checks.
- `build_runtime_bundle.sh` — build the packaged runtime bundle.

## HTTPS and NGINX recovery

- `install_cert_simple.sh`, `install_letsencrypt_cert.sh`, `ssm_install_cert.py`
- `fix_nginx_*.sh`, `fix_nginx_simple.py`, `fix_and_install_cert.sh`
- `complete_cert_install.sh`, `fix_qdrant_ui_nginx.sh`

Read [Let's Encrypt guidance](README_LETSENCRYPT.md) and the
[manual NGINX recovery guide](MANUAL_NGINX_FIX.md) before using recovery scripts.
These scripts can modify a running host and should be treated as operator tools, not
as part of the normal deployment path.

## Runtime health patches

- `patch_qdrant_healthcheck.py`
- `patch_webhook_healthcheck.py`
- [Health-check patch notes](README_HEALTHCHECK_PATCH.md)

Run scripts from the repository root unless their documentation explicitly says otherwise.
