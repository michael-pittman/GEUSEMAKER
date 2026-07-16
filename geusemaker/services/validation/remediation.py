"""Remediation hints for common validation failures."""

REMEDIATIONS: dict[str, str] = {
    "ec2_status": "Wait for EC2 status checks or reboot the instance; verify subnet and SG allow required traffic.",
    "efs_mount": "Verify EFS mount targets and SG allow NFS; remount /mnt/efs and ensure correct filesystem ID.",
    "n8n": "Check Docker service for n8n, restart container, verify host NGINX is running and SG allows port 80/443.",
    "ollama": "Check Ollama container logs; ensure model pull completed and NGINX route /api/ollama/ responds.",
    "qdrant": "Check Qdrant container logs and NGINX route /qdrant/; validate volume permissions on EFS.",
    "crawl4ai": "Check Crawl4AI service and NGINX route /crawl4ai/; confirm environment variables are set.",
    "postgres": "Verify Postgres container is running (docker inspect postgres); it is only reachable inside the instance.",
}


def remediation_for(key: str) -> str | None:
    """Return remediation guidance for a failure key."""
    return REMEDIATIONS.get(key)


__all__ = ["remediation_for"]
