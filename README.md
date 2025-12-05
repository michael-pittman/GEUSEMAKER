# GeuseMaker

CLI for deploying and managing the GeuseMaker AI infrastructure stack on AWS using Python, Click, Rich, Pydantic, and Boto3.

## Getting Started

```bash
# 1. Ensure Python 3.12+ is installed
python3.12 --version  # Should show Python 3.12.x

# 2. Create and activate a virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Verify installation
geusemaker --help
```

## Usage

- **Interactive deploy (default)**: run `geusemaker deploy` with no flags to launch a guided wizard that discovers your VPC/subnets/SGs, previews costs, and writes state under `~/.geusemaker`. Use `--no-interactive` to force non-interactive mode when scripting.
- **Config file deploy**: `geusemaker deploy --config path/to/config.yaml` (YAML or JSON). CLI flags override file values when provided.
- **Reuse an existing security group**: pass `--security-group-id sg-123` (must belong to the chosen VPC). Validation now confirms VPC membership and required ingress (22, 80, 5678, 2049); otherwise the deploy fails and suggests remediation.
- **Reuse a VPC without internet routing**: pass `--vpc-id vpc-123 --attach-internet-gateway` to let GeuseMaker attach an Internet Gateway and configure public routes for your compute subnet.

## Development

- Lint: `./scripts/lint.sh`
- Tests: `./scripts/test.sh`

## License

MIT
