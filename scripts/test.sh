#!/usr/bin/env bash
set -euo pipefail

# Use venv if available, otherwise assume tools are in PATH
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/../venv"

if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
fi

# Dummy AWS credentials so the boto3 credential chain resolves offline and the
# unit suite (moto-mocked) can never reach a real account. Overridable if the
# caller has already exported real creds for an integration run.
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-testing}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-testing}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
unset AWS_PROFILE

pytest
