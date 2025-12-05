"""Remediation hints for common validation failures."""

REMEDIATIONS: dict[str, str] = {
    "ec2_status": "Wait for EC2 status checks or reboot the instance; verify subnet and SG allow required traffic.",
    "efs_mount": "Verify EFS mount targets and SG allow NFS; remount /mnt/efs and ensure correct filesystem ID.",
    "n8n": "Check Docker service for n8n, restart container, verify port 5678 is open in SG.",
    "ollama": "Check Ollama container logs; ensure model pull completed and port 11434 is open.",
    "qdrant": "Check Qdrant container logs and port 6333; validate volume permissions on EFS.",
    "crawl4ai": "Check Crawl4AI service and port 11235; confirm environment variables are set.",
    "postgres": "Verify Postgres container is running and port 5432 is reachable; check credentials and volume.",
}


def remediation_for(key: str) -> str | None:
    """Return remediation guidance for a failure key."""
    return REMEDIATIONS.get(key)


__all__ = ["remediation_for"]
