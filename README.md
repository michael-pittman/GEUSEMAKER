# GeuseMaker

**AI Infrastructure Deployment Platform** - Deploy a complete AI application stack (n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL) on AWS with intelligent cost optimization using spot instances.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

✨ **Complete AI Stack** - Workflow automation (n8n), LLM inference (Ollama), vector database (Qdrant), web scraping (Crawl4AI)
💰 **Cost Optimized** - Intelligent spot instance selection with 50-70% savings
🚀 **Fast Deployment** - Interactive wizard with real-time cost preview
📊 **Monitoring Built-in** - Health checks, log streaming, deployment status
🔒 **Secure by Default** - IAM-based EFS authentication, VPC isolation
🎯 **Three Tiers** - Dev (Tier 1), Production (Tier 2 with ALB), GPU (Tier 3 planned)

## Quick Start

### Installation

```bash
# 1. Ensure Python 3.12+ is installed
python3.12 --version  # Should show Python 3.12.x

# 2. Create and activate a virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install GeuseMaker
pip install -e ".[dev]"

# 4. Verify installation
geusemaker --help
```

### Deploy Your First Stack

```bash
# Interactive deployment (recommended for first-time users)
geusemaker deploy

# The wizard will guide you through:
# 1. Stack naming
# 2. Region selection
# 3. Tier choice (1=Dev, 2=Production, 3=GPU)
# 4. Instance type and spot preferences
# 5. Network configuration (VPC/subnet/security group)
# 6. Cost preview
# 7. Resource confirmation
```

**What gets deployed:**
- **Compute**: EC2 instance (spot or on-demand) with Deep Learning AMI
- **Storage**: EFS filesystem for persistent data (n8n workflows, Ollama models, Qdrant indexes, PostgreSQL data)
- **Network**: VPC, subnet, security group, internet gateway
- **IAM**: Instance profile for EFS mount authentication
- **Services**: n8n (5678), Ollama (11434), Qdrant (6333), Crawl4AI (11235), PostgreSQL (5432)
- **Database**: PostgreSQL configured for n8n (auto-configured, no manual setup needed)
- **Security**: Auto-generated encryption key for n8n credential storage

## Deployment Modes

### 1. Interactive Mode (Default)

Guided wizard with VPC/subnet/SG discovery, cost preview, and resource confirmation:

```bash
geusemaker deploy
```

**Features:**
- Automatic AWS resource discovery
- Real-time cost estimation
- Spot instance price analysis
- Complete resource summary before deployment
- Graceful error handling with retry options

### 2. Non-Interactive Mode

For scripting and automation:

```bash
geusemaker deploy \
  --no-interactive \
  --stack-name my-ai-stack \
  --region us-east-1 \
  --tier 1 \
  --instance-type t3.large \
  --use-spot \
  --vpc-id vpc-123456 \
  --subnet-id subnet-789012 \
  --security-group-id sg-345678
```

### 3. Config File Mode

YAML/JSON configuration with CLI flag overrides:

```bash
# Create config file
cat > deployment.yaml <<EOF
stack_name: my-ai-stack
region: us-east-1
tier: 1

# Instance configuration
instance_type: t3.large
use_spot: true
os_type: amazon-linux-2023

# Network (optional - created if omitted)
vpc_id: vpc-123456
subnet_id: subnet-789012
security_group_id: sg-345678

# Optimization
use_runtime_bundle: true
EOF

# Deploy with config
geusemaker deploy --config deployment.yaml

# Override specific settings
geusemaker deploy --config deployment.yaml --instance-type t3.xlarge
```

## Monitoring & Management

### Check Deployment Status

```bash
# Show instance state and service health
geusemaker status my-ai-stack

# Example output:
# ┌─ Instance Status ─────────────────────────┐
# │ Instance ID    i-0123456789abcdef0        │
# │ State          running                    │
# │ Instance Type  t3.large                   │
# │ Public IP      54.123.45.67               │
# └───────────────────────────────────────────┘
# ┌─ Service Health ──────────────────────────┐
# │ Service      Port   Status                │
# │ n8n          5678   ✓ healthy             │
# │ Qdrant       6333   ✓ healthy             │
# │ Ollama       11434  ✓ healthy             │
# │ Crawl4AI     11235  ✓ healthy             │
# │ PostgreSQL   5432   ✓ healthy             │
# └───────────────────────────────────────────┘
```

### View Logs

GeuseMaker provides comprehensive logging infrastructure with multiple log files:

#### Log File Locations on EC2 Instance

| Log File | Location | Purpose |
|----------|----------|---------|
| **UserData Initialization** | `/var/log/geusemaker-userdata.log` | Main initialization script output (system setup, Docker install, service startup) |
| **Model Preloading** | `/var/log/geusemaker/model-preload.log` | Ollama model downloads (qwen2.5:1.5b-instruct, bge-small, GPU models) |
| **EFS Mount** | `/var/log/amazon/efs/mount.log` | EFS mount diagnostics and errors |
| **Cloud-Init** | `/var/log/cloud-init-output.log` | AWS cloud-init system logs (fallback) |
| **Docker Containers** | `docker logs <container>` | Individual service logs (n8n, ollama, qdrant, crawl4ai, postgres) |

#### Fetch Logs via CLI

```bash
# View UserData initialization logs (last 100 lines)
geusemaker logs my-ai-stack

# Stream UserData logs in real-time (during deployment)
geusemaker logs my-ai-stack --follow

# View specific service logs
geusemaker logs my-ai-stack --service n8n --tail 200
geusemaker logs my-ai-stack --service ollama --tail 500
geusemaker logs my-ai-stack --service qdrant
geusemaker logs my-ai-stack --service crawl4ai
geusemaker logs my-ai-stack --service postgres

# Available services: userdata, n8n, ollama, qdrant, crawl4ai, postgres
```

#### Stream Logs Directly from Server

If you have SSH access to the EC2 instance:

```bash
# Get instance IP
PUBLIC_IP=$(geusemaker status my-ai-stack --output json | jq -r '.data.instance.public_ip')

# SSH to instance (replace key-pair.pem with your key)
ssh -i ~/.ssh/key-pair.pem ec2-user@$PUBLIC_IP

# Stream UserData logs (initialization progress)
tail -f /var/log/geusemaker-userdata.log

# Stream model preloading logs (Ollama downloads)
tail -f /var/log/geusemaker/model-preload.log

# Stream container logs (pick one)
docker logs -f n8n
docker logs -f ollama
docker logs -f qdrant
docker logs -f crawl4ai
docker logs -f postgres

# View all logs at once (advanced)
tail -f /var/log/geusemaker-userdata.log \
         /var/log/geusemaker/model-preload.log
```

### Access Services

Once deployment completes and health checks pass:

```bash
# Get public IP
geusemaker status my-ai-stack

# Access web interfaces
# n8n:      http://<public-ip>:5678
# Qdrant:   http://<public-ip>:6333/dashboard
# Ollama:   http://<public-ip>:11434/api/tags
# Crawl4AI: http://<public-ip>:11235/docs

# Test Ollama API
curl http://<public-ip>:11434/api/chat -d '{
  "model": "qwen2.5:1.5b-instruct",
  "messages": [{"role": "user", "content": "Hello!"}]
}'

# List preloaded models
curl http://<public-ip>:11434/api/tags
```

### Configure n8n Credentials

GeuseMaker **automatically preloads** n8n with PostgreSQL credentials during deployment, so workflows can run immediately without manual setup.

#### Automatic Credential Preloading

During deployment, GeuseMaker automatically:
- ✅ Creates PostgreSQL credential (`postgres-local`) with connection details
- ✅ Waits for n8n API to be ready before creating credentials
- ✅ Handles authentication via owner API key or basic auth (if configured)

**To enable automatic credential creation**, set one of these environment variables in your deployment config:

```yaml
# Option 1: Owner API key (recommended)
custom_env:
  N8N_USER_MANAGEMENT_OWNER_API_KEY: "your-api-key-here"

# Option 2: Basic auth
custom_env:
  N8N_BASIC_AUTH_ACTIVE: "true"
  N8N_BASIC_AUTH_USER: "admin"
  N8N_BASIC_AUTH_PASSWORD: "your-password"
```

**If API authentication isn't configured**, credentials will be created manually after first n8n login. The deployment script will log instructions for manual setup.

#### Manual Credential Configuration

If automatic preloading didn't work or you need to add additional credentials:

#### 1. **Ollama Connection** (Required for AI workflows)

In n8n, create a new **Ollama** credential:

- **Base URL**: `http://ollama:11434`
  - ⚠️ **Important**: Use `ollama` (container name), NOT `localhost`
  - n8n runs in Docker and must use Docker network hostnames
- **API Key**: (leave empty - no authentication required)

**Why `ollama:11434`?**
- Both n8n and Ollama run in Docker containers on the same network
- Docker Compose automatically creates DNS resolution between containers
- `localhost` inside the n8n container refers to itself, not other containers

#### 2. **PostgreSQL Database** (Auto-configured & Preloaded)

n8n is automatically configured to use PostgreSQL, and the credential is **preloaded** during deployment:

- **Credential Name**: `PostgreSQL Local` (ID: `postgres-local`)
- **Host**: `postgres` (container name)
- **Port**: `5432`
- **Database**: `geusemaker`
- **User**: `geusemaker`
- **Password**: Set during deployment (from `postgres_password` config)

**✅ Credential is automatically created** - workflows referencing `postgres-local` will work immediately.

**To verify credential was created:**
1. Log into n8n UI: `http://<public-ip>:5678`
2. Go to **Credentials** → Look for "PostgreSQL Local"
3. If missing, see "Manual Credential Setup" below

**To retrieve the PostgreSQL password** (if needed for direct database access):
```bash
# Get the public IP of your instance
PUBLIC_IP=$(geusemaker status <stack-name> --output json | jq -r '.data.instance.public_ip')

# SSH to the instance
ssh -i ~/.ssh/key.pem ubuntu@$PUBLIC_IP  # or ec2-user@ for Amazon Linux

# Get password from Docker container environment
docker exec n8n env | grep POSTGRES_PASSWORD

# Or from PostgreSQL container directly
docker exec postgres env | grep POSTGRES_PASSWORD

# Or print just the password value
docker exec postgres printenv POSTGRES_PASSWORD
```

#### 3. **Qdrant Connection** (Optional, for vector workflows)

If you need to connect n8n to Qdrant:

- **Base URL**: `http://qdrant:6333`
- **API Key**: (leave empty - no authentication required)

#### 4. **Crawl4AI Connection** (Optional, for web scraping workflows)

If you need to connect n8n to Crawl4AI:

- **Base URL**: `http://crawl4ai:11235`
- **API Key**: (leave empty - no authentication required)

#### Credential Encryption

n8n automatically generates an encryption key (`N8N_ENCRYPTION_KEY`) during deployment to securely store credentials. This key is:
- Generated automatically (32 random bytes)
- Stored in `/mnt/efs/runtime.env` on the EC2 instance
- Used to encrypt all credentials stored in n8n workflows
- **Critical**: If you lose this key, you cannot decrypt existing credentials

#### Troubleshooting Credential Preloading

If credentials weren't automatically created, check the deployment logs:

```bash
# View credential preloading logs
geusemaker logs my-stack | grep -i credential

# Or SSH to instance and check
ssh -i ~/.ssh/key.pem ec2-user@<public-ip>
tail -100 /var/log/geusemaker-userdata.log | grep -i credential
```

**Common issues:**
- **n8n API not ready**: Wait a few minutes after deployment, then manually create credentials
- **Authentication not configured**: Set `N8N_USER_MANAGEMENT_OWNER_API_KEY` or basic auth env vars
- **Credential already exists**: Safe to ignore - existing credential will be used

**Manual credential creation** (if automatic preloading failed):
1. Log into n8n: `http://<public-ip>:5678`
2. Go to **Credentials** → **Add Credential** → **PostgreSQL**
3. Use connection details from "PostgreSQL Database" section above

**To view the encryption key** (if needed for backup):
```bash
ssh -i ~/.ssh/key.pem ec2-user@<public-ip>
cat /mnt/efs/runtime.env | grep N8N_ENCRYPTION_KEY
```

**⚠️ Security Note**: Keep the encryption key secure. If you need to migrate n8n data, you must preserve this key.

### Cost Tracking

```bash
# Show cost breakdown
geusemaker cost my-ai-stack

# Example output:
# ┌─ Monthly Cost Estimate ───────────────────┐
# │ EC2 (t3.large spot)    $36.50             │
# │ EFS Storage (10GB)     $3.00              │
# │ Data Transfer          $0.50              │
# │ Total                  $40.00/month       │
# │                                            │
# │ Savings (vs on-demand): 50% ($36.50)      │
# └───────────────────────────────────────────┘
```

### Cleanup

```bash
# Destroy deployment and all resources
geusemaker destroy my-ai-stack

# This removes:
# - EC2 instance
# - EFS filesystem and mount target
# - IAM role and instance profile
# - VPC, subnet, security group (if created by GeuseMaker)
# - State file from ~/.geusemaker/

# Preserve EFS data (delete compute/network, keep persistent storage)
geusemaker destroy my-ai-stack --preserve-efs

# Use case: Stop expensive compute while retaining workflows/models/data
# - Deletes: EC2 instance, IAM role, VPC/subnet/SG (if created)
# - Preserves: EFS filesystem with all data (n8n workflows, Ollama models, Qdrant indexes)
# - Benefit: Recreate deployment later from existing data without re-downloading models
```

## Advanced Usage

### Custom AMI

```bash
# Use your own AMI instead of auto-selection
geusemaker deploy \
  --stack-name my-stack \
  --ami-id ami-0123456789abcdef0
```

### Reuse Existing Network Resources

```bash
# Reuse VPC and add internet gateway
geusemaker deploy \
  --vpc-id vpc-123456 \
  --attach-internet-gateway

# Reuse security group (must have ports 22, 80, 5678, 2049)
geusemaker deploy \
  --security-group-id sg-345678
```

### Skip Pre-Deployment Validation

```bash
# Bypass quota/AMI/region checks (use with caution)
geusemaker deploy --skip-validation
```

### Discover Lost Deployments

```bash
# Recover state from AWS resources (if state files lost)
geusemaker list --discover-from-aws --region us-east-1
```

## Troubleshooting

### Deployment Stuck or Failed

```bash
# Stream initialization logs
geusemaker logs my-ai-stack --follow

# Check for errors in UserData script
geusemaker logs my-ai-stack | grep -i error

# SSH to instance and check status
ssh -i ~/.ssh/key.pem ec2-user@<public-ip>
tail -100 /var/log/geusemaker-userdata.log
```

### Services Not Starting

```bash
# Check service health
geusemaker status my-ai-stack

# View container logs
geusemaker logs my-ai-stack --service ollama --tail 500
geusemaker logs my-ai-stack --service n8n --tail 500

# SSH and check Docker status
ssh -i ~/.ssh/key.pem ec2-user@<public-ip>
docker ps -a
docker logs ollama
```

### Model Preloading Issues

```bash
# Check model preload progress
ssh -i ~/.ssh/key.pem ec2-user@<public-ip>
tail -f /var/log/geusemaker/model-preload.log

# Or via CLI (requires SSM access)
# Note: model-preload.log is not directly accessible via geusemaker logs
# Use SSH or check userdata logs for model preload status
```

### EFS Mount Problems

```bash
# SSH to instance and check EFS mount
ssh -i ~/.ssh/key.pem ec2-user@<public-ip>
df -h | grep efs
cat /var/log/amazon/efs/mount.log
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/geusemaker.git
cd geusemaker

# Install with dev dependencies
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run linters
./scripts/lint.sh

# Run tests
./scripts/test.sh
```

### Run Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/ -v

# Specific test file
pytest tests/unit/test_services/test_ec2.py -v

# With coverage
pytest --cov=geusemaker --cov-report=term-missing
```

## Architecture

GeuseMaker uses a **layered monolith** architecture:

```
CLI → Orchestration → Services → Infrastructure
 ↓         ↓             ↓            ↓
Click   Tier1/2/3    EC2/EFS/VPC   Boto3
Rich    Workflow     IAM/ALB       State
```

**Key components:**
- **CLI Layer**: Click commands, Rich UI, questionary prompts
- **Orchestration**: Deployment workflows (Tier 1, 2, 3)
- **Services**: AWS resource managers (EC2, EFS, VPC, IAM, ALB, etc.)
- **Infrastructure**: Boto3 clients, state persistence, error handling

**Storage architecture:**
- **Docker internals** → Local EBS (ephemeral)
- **Application data** → EFS (persistent via bind mounts)
  - `/mnt/efs/n8n` → n8n workflows
  - `/mnt/efs/ollama` → Ollama models
  - `/mnt/efs/qdrant` → Qdrant indexes
  - `/mnt/efs/postgres` → PostgreSQL data

## Documentation

- **Project Guide**: [CLAUDE.md](CLAUDE.md) - Comprehensive coding patterns and architecture
- **PRD**: [docs/PRD.md](docs/PRD.md) - Product requirements
- **Architecture**: [docs/architecture.md](docs/architecture.md) - System design
- **Stories**: [docs/stories/](docs/stories/) - Implementation details
- **Epics**: [docs/epics/](docs/epics/) - Feature epics

## License

MIT License - see [LICENSE](LICENSE) for details

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/geusemaker/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/geusemaker/discussions)
