# Docker Healthcheck Patch (Qdrant)

The Qdrant Docker image does not include `curl` or `wget`, so the default healthcheck fails. This patch replaces it with a bash TCP port check.

## Compose File Paths (GeuseMaker)

| Deployment mode | Compose path |
|-----------------|--------------|
| With runtime bundle | `/opt/geusemaker/runtime/docker-compose.yml` |
| Without bundle | `/root/docker-compose.yml` |

## Apply via SSM

```bash
# 1. Copy script to instance and run
SCRIPT_B64=$(base64 -i scripts/patch_qdrant_healthcheck.py | tr -d '\n')
aws ssm send-command \
  --instance-ids INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"echo $SCRIPT_B64 | base64 -d > /tmp/patch_qdrant.py\", \"python3 /tmp/patch_qdrant.py\"]" \
  --timeout-seconds 60

# 2. Recreate Qdrant (use the compose dir that matches your deploy)
# With runtime bundle:
aws ssm send-command --instance-ids INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/geusemaker/runtime && docker compose --env-file runtime.env up -d --force-recreate qdrant"]' \
  --timeout-seconds 90

# Without bundle (compose in /root):
aws ssm send-command --instance-ids INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /root && docker compose --env-file runtime.env up -d --force-recreate qdrant"]' \
  --timeout-seconds 90
```

## Webhook-alias (port 8088)

If you have a custom `webhook-alias` nginx container listening on port 8088, ensure its healthcheck uses `http://localhost:8088/healthz` (not port 80).
