# Let's Encrypt Certificate Installation Guide

This guide explains how to install a trusted SSL/TLS certificate from Let's Encrypt on your GeuseMaker GPU server.

## Prerequisites

1. **Domain Name**: You need a domain name pointing to your GPU server (e.g., `gpu.geuse.io`, `ollama.geuse.io`)
2. **DNS Access**: You must be able to create DNS A records for your domain
3. **Port 80 Access**: Let's Encrypt validation requires HTTP access on port 80
4. **SSH Access**: You need SSH access to the EC2 instance

## Quick Start

### Step 1: Set Up DNS

Before requesting a certificate, ensure your domain points to the GPU server's public IP:

```bash
# Get the public IP of your GPU server
PUBLIC_IP=$(geusemaker status <stack-name> --output json | jq -r '.data.instance.public_ip')

# Create DNS A record:
# Domain: gpu.geuse.io (or your chosen subdomain)
# Type: A
# Value: $PUBLIC_IP
# TTL: 300 (5 minutes)
```

**Example DNS records:**
- `gpu.geuse.io` → `54.163.106.7`
- `ollama.geuse.io` → `54.163.106.7`
- `ai.geuse.io` → `54.163.106.7`

### Step 2: Verify DNS Propagation

Wait for DNS to propagate (usually 1-5 minutes):

```bash
# Check DNS resolution
dig +short gpu.geuse.io
# Should return: 54.163.106.7

# Or use nslookup
nslookup gpu.geuse.io
```

### Step 3: Install Certificate

**Option A: Using SSH (Recommended)**

```bash
# SSH to your GPU server
PUBLIC_IP=$(geusemaker status <stack-name> --output json | jq -r '.data.instance.public_ip')
ssh ubuntu@$PUBLIC_IP  # or ec2-user@ for Amazon Linux

# Download and run the installation script
curl -O https://raw.githubusercontent.com/yourusername/geusemaker/main/scripts/install_letsencrypt_cert.sh
chmod +x install_letsencrypt_cert.sh
sudo ./install_letsencrypt_cert.sh gpu.geuse.io admin@geuse.io
```

**Option B: Using AWS Systems Manager (No SSH Keys)**

```bash
# Get instance ID
INSTANCE_ID=$(geusemaker status <stack-name> --output json | jq -r '.data.instance.instance_id')

# Start SSM session
aws ssm start-session --target $INSTANCE_ID --region us-east-1

# Once connected, download and run the script
curl -O https://raw.githubusercontent.com/yourusername/geusemaker/main/scripts/install_letsencrypt_cert.sh
chmod +x install_letsencrypt_cert.sh
sudo ./install_letsencrypt_cert.sh gpu.geuse.io admin@geuse.io
```

**Option C: Copy Script to Instance**

```bash
# Copy script to instance via SCP
scp scripts/install_letsencrypt_cert.sh ubuntu@$PUBLIC_IP:/tmp/

# SSH and run
ssh ubuntu@$PUBLIC_IP
sudo bash /tmp/install_letsencrypt_cert.sh gpu.geuse.io admin@geuse.io
```

### Step 4: Verify Installation

```bash
# Check certificate details
sudo certbot certificates

# Test HTTPS connection
curl -I https://gpu.geuse.io

# View certificate expiration
echo | openssl s_client -connect gpu.geuse.io:443 -servername gpu.geuse.io 2>/dev/null | openssl x509 -noout -dates
```

## What the Script Does

1. **Installs certbot** (Let's Encrypt client) based on your OS
2. **Updates NGINX config** to use your domain name
3. **Requests certificate** from Let's Encrypt using HTTP-01 validation
4. **Updates NGINX** to use Let's Encrypt certificates instead of self-signed
5. **Sets up auto-renewal** via cron job (certificates expire every 90 days)

## Troubleshooting

### Error: "Failed to obtain certificate"

**DNS not pointing to server:**
```bash
# Verify DNS resolution
dig +short gpu.geuse.io
# Should return your server's public IP

# If not, update DNS records and wait for propagation
```

**Port 80 blocked:**
```bash
# Check security group allows inbound HTTP
aws ec2 describe-security-groups --group-ids sg-xxxxx --region us-east-1

# Add rule if missing:
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 \
  --region us-east-1
```

**NGINX not running:**
```bash
sudo systemctl status nginx
sudo systemctl start nginx
```

### Error: "Connection refused"

Check that NGINX is listening on port 80:
```bash
sudo netstat -tlnp | grep :80
sudo ss -tlnp | grep :80
```

### Certificate Renewal Issues

Test renewal manually:
```bash
sudo certbot renew --dry-run
```

If renewal fails, check logs:
```bash
sudo tail -f /var/log/letsencrypt/letsencrypt.log
```

## Alternative: Upgrade to Tier 2/3 (Long-term Solution)

For production deployments, consider upgrading to **Tier 2** (ALB with ACM) or **Tier 3** (CloudFront + ALB):

### Benefits:
- ✅ AWS-managed certificates (no renewal needed)
- ✅ Automatic certificate rotation
- ✅ High availability with load balancer
- ✅ Better for production workloads

### Migration Steps:

1. **Request ACM Certificate:**
```bash
aws acm request-certificate \
  --domain-name "*.geuse.io" \
  --subject-alternative-names "geuse.io" \
  --validation-method DNS \
  --region us-east-1
```

2. **Validate Domain:**
```bash
# Get validation records
aws acm describe-certificate \
  --certificate-arn arn:aws:acm:us-east-1:123456789012:certificate/abc123 \
  --region us-east-1

# Add CNAME records to DNS for validation
```

3. **Redeploy as Tier 2:**
```bash
# Destroy current Tier 1 deployment
geusemaker destroy <stack-name> --preserve-efs

# Deploy as Tier 2 with ACM certificate
geusemaker deploy \
  --stack-name <stack-name> \
  --tier automation \
  --alb-certificate-arn arn:aws:acm:us-east-1:123456789012:certificate/abc123 \
  --efs-id fs-xxxxx  # Reuse existing EFS
```

## Certificate Locations

After installation, certificates are stored at:
- **Certificate**: `/etc/letsencrypt/live/<domain>/fullchain.pem`
- **Private Key**: `/etc/letsencrypt/live/<domain>/privkey.pem`
- **NGINX Config**: `/etc/nginx/conf.d/default.conf`

## Auto-Renewal

Certificates auto-renew via:
1. **certbot timer** (systemd) - checks twice daily
2. **cron job** - fallback if systemd not available
3. **Renewal hook** - automatically reloads NGINX after renewal

Certificates expire every **90 days** and renew **30 days** before expiration.

## Security Notes

- ✅ Let's Encrypt certificates are trusted by all major browsers
- ✅ Certificates auto-renew before expiration
- ✅ Private keys are stored securely (`600` permissions)
- ✅ NGINX reloads automatically after renewal

## Support

For issues or questions:
- Let's Encrypt docs: https://letsencrypt.org/docs/
- Certbot docs: https://eff-certbot.readthedocs.io/
- GeuseMaker issues: https://github.com/yourusername/geusemaker/issues
