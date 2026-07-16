# Configuration examples

This directory contains version-controlled examples and defaults:

- `defaults.yml` — default GeuseMaker deployment values.
- `ai-stack.yml` — example AI-stack configuration.
- `logging.yml` — logging configuration example.

Deploy from a YAML or JSON file with:

```bash
geusemaker deploy --config config/defaults.yml
```

Command-line flags override file values. Keep credentials and environment-specific
secrets out of these files; use the AWS credential chain and local environment variables.
