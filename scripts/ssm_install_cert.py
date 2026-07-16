#!/usr/bin/env python3
"""Helper script to install Let's Encrypt certificate via SSM."""

import json
import subprocess
import sys
import time
from pathlib import Path

def read_script():
    """Read the installation script."""
    script_path = Path(__file__).parent / "install_letsencrypt_cert.sh"
    return script_path.read_text()

def send_ssm_command(instance_id: str, script_content: str, domain: str, email: str, region: str = "us-east-1"):
    """Send SSM command to copy and execute the script."""
    
    # Create commands to write script and execute it
    commands = [
        f"cat > /tmp/install_letsencrypt_cert.sh << 'SCRIPTEND'\n{script_content}\nSCRIPTEND",
        "chmod +x /tmp/install_letsencrypt_cert.sh",
        f"sudo /tmp/install_letsencrypt_cert.sh {domain} {email}"
    ]
    
    # Send command via AWS CLI
    cmd = [
        "aws", "ssm", "send-command",
        "--instance-ids", instance_id,
        "--document-name", "AWS-RunShellScript",
        "--parameters", json.dumps({"commands": commands}),
        "--region", region,
        "--query", "Command.CommandId",
        "--output", "text"
    ]
    
    print(f"📤 Sending SSM command to instance {instance_id}...")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    command_id = result.stdout.strip()
    print(f"✅ Command sent. Command ID: {command_id}")
    
    return command_id

def wait_for_command(instance_id: str, command_id: str, region: str = "us-east-1", max_wait: int = 300):
    """Wait for SSM command to complete and return output."""
    
    print(f"⏳ Waiting for command to complete (max {max_wait}s)...")
    
    start_time = time.time()
    while time.time() - start_time < max_wait:
        cmd = [
            "aws", "ssm", "get-command-invocation",
            "--command-id", command_id,
            "--instance-id", instance_id,
            "--region", region,
            "--query", "[Status,StandardOutputContent,StandardErrorContent]",
            "--output", "json"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            status = data[0]
            stdout = data[1] if len(data) > 1 else ""
            stderr = data[2] if len(data) > 2 else ""
            
            if status in ["Success", "Failed", "Cancelled", "TimedOut"]:
                return status, stdout, stderr
            
            print(f"   Status: {status}... waiting")
            time.sleep(5)
        else:
            print(f"   Checking status...")
            time.sleep(5)
    
    return "TimedOut", "", "Command did not complete within timeout"

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 ssm_install_cert.py <instance-id> <domain> <email> [region]")
        print("Example: python3 ssm_install_cert.py i-01223c66a2daa9cba ai.geuse.io admin@geuse.io us-east-1")
        sys.exit(1)
    
    instance_id = sys.argv[1]
    domain = sys.argv[2]
    email = sys.argv[3]
    region = sys.argv[4] if len(sys.argv) > 4 else "us-east-1"
    
    print(f"🔒 Installing Let's Encrypt certificate for {domain}")
    print(f"   Instance: {instance_id}")
    print(f"   Email: {email}")
    print(f"   Region: {region}")
    print()
    
    # Read script content
    script_content = read_script()
    
    # Send command
    command_id = send_ssm_command(instance_id, script_content, domain, email, region)
    
    # Wait for completion
    status, stdout, stderr = wait_for_command(instance_id, command_id, region)
    
    # Print results
    print()
    print("=" * 60)
    print(f"Command Status: {status}")
    print("=" * 60)
    
    if stdout:
        print("\n📤 Output:")
        print(stdout)
    
    if stderr:
        print("\n⚠️  Errors:")
        print(stderr)
    
    if status == "Success":
        print("\n✅ Certificate installation completed successfully!")
        print(f"\n🌐 Access your services at:")
        print(f"   n8n: https://{domain}")
        print(f"   Ollama API: https://{domain}/api/ollama/")
        print(f"   Qdrant Dashboard: https://{domain}/qdrant-ui/")
    else:
        print(f"\n❌ Installation failed with status: {status}")
        if "DNS" in stderr or "dns" in stderr.lower():
            print("\n💡 Tip: Make sure DNS is set up:")
            print(f"   Create A record: {domain} → 54.163.106.7")
        sys.exit(1)

if __name__ == "__main__":
    main()
