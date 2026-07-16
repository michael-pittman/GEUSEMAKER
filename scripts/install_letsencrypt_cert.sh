#!/bin/bash
# Install Let's Encrypt SSL certificate for GeuseMaker GPU server
# Usage: ./install_letsencrypt_cert.sh <domain-name> [email]

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-admin@geuse.io}"

if [ -z "$DOMAIN" ]; then
    echo "Usage: $0 <domain-name> [email]"
    echo "Example: $0 gpu.geuse.io admin@geuse.io"
    exit 1
fi

echo "🔒 Installing Let's Encrypt certificate for $DOMAIN"

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_FAMILY="${ID:-unknown}"
else
    OS_FAMILY="unknown"
fi

# Install certbot based on OS
echo "📦 Installing certbot..."
if [ "$OS_FAMILY" = "ubuntu" ] || [ "$OS_FAMILY" = "debian" ]; then
    apt-get update -qq
    apt-get install -y certbot python3-certbot-nginx
elif [ "$OS_FAMILY" = "amzn" ] || [ "$OS_FAMILY" = "rhel" ] || [ "$OS_FAMILY" = "fedora" ]; then
    # Amazon Linux 2023 uses dnf
    if command -v dnf >/dev/null 2>&1; then
        dnf install -y certbot python3-certbot-nginx
    else
        yum install -y certbot python3-certbot-nginx
    fi
else
    echo "⚠️  Unknown OS family: $OS_FAMILY"
    echo "Attempting to install certbot via snap (fallback)..."
    if command -v snap >/dev/null 2>&1; then
        snap install --classic certbot
        ln -sf /snap/bin/certbot /usr/bin/certbot
    else
        echo "❌ Cannot install certbot. Please install manually."
        exit 1
    fi
fi

# Verify certbot installation
if ! command -v certbot >/dev/null 2>&1; then
    echo "❌ certbot installation failed"
    exit 1
fi

echo "✅ certbot installed successfully"

# Backup existing NGINX config
NGINX_CONF="/etc/nginx/conf.d/default.conf"
if [ -f "$NGINX_CONF" ]; then
    BACKUP="${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$NGINX_CONF" "$BACKUP"
    echo "📋 Backed up NGINX config to $BACKUP"
fi

# Update NGINX config to use domain name instead of wildcard
# This is required for Let's Encrypt validation
echo "🔧 Updating NGINX configuration for domain: $DOMAIN"
sed -i "s/server_name _;/server_name $DOMAIN;/g" "$NGINX_CONF" || {
    echo "⚠️  Could not update server_name in NGINX config. Please update manually."
}

# Ensure HTTP server block allows Let's Encrypt validation
# First, remove any existing malformed ACME challenge locations
sed -i '/\.well-known\/acme-challenge/d' "$NGINX_CONF" || true

# Replace entire HTTP server block with clean version including ACME challenge
python3 << 'PYTHON_EOF'
nginx_conf = "/etc/nginx/conf.d/default.conf"
with open(nginx_conf, 'r') as f:
    content = f.read()

# Check if already added
if '/.well-known/acme-challenge' in content:
    print("✅ ACME challenge location already exists")
else:
    import re
    
    # Extract domain name from server_name (should be ai.geuse.io after sed replacement)
    server_name_match = re.search(r'server_name\s+([^;]+);', content)
    domain = server_name_match.group(1).strip() if server_name_match else "_"
    
    # Replace entire HTTP server block (from "server {" with "listen 80" to closing "}")
    # Match HTTP server block more precisely
    http_block_pattern = r'server \{[^}]*listen 80;[^}]*listen \[::\]:80;[^}]*server_name[^}]*;\s*[^}]*location[^}]*return 301[^}]*\}'
    
    # New HTTP server block with ACME challenge
    new_http_block = f'''server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {{
        root /var/www/html;
        try_files $uri =404;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}'''
    
    # Try to replace HTTP server block
    new_content = re.sub(http_block_pattern, new_http_block, content, flags=re.DOTALL)
    
    if new_content == content:
        # Fallback: find lines and replace manually
        lines = content.split('\n')
        new_lines = []
        in_http_block = False
        http_block_start = -1
        http_block_end = -1
        brace_count = 0
        
        for i, line in enumerate(lines):
            if 'server {' in line:
                # Check if this is HTTP server block
                lookahead = '\n'.join(lines[i:min(i+10, len(lines))])
                if 'listen 80;' in lookahead:
                    in_http_block = True
                    http_block_start = i
                    brace_count = 1
                    continue
            
            if in_http_block:
                if '{' in line:
                    brace_count += line.count('{')
                if '}' in line:
                    brace_count -= line.count('}')
                    if brace_count == 0:
                        http_block_end = i
                        # Replace the entire HTTP block
                        indent = '    '
                        new_lines.append('server {')
                        new_lines.append(f'{indent}listen 80;')
                        new_lines.append(f'{indent}listen [::]:80;')
                        new_lines.append(f'{indent}server_name {domain};')
                        new_lines.append('')
                        new_lines.append(indent + "# Let's Encrypt validation")
                        new_lines.append(indent + "location /.well-known/acme-challenge/ {")
                        new_lines.append(indent + "    root /var/www/html;")
                        new_lines.append(indent + "    try_files $uri =404;")
                        new_lines.append(indent + "}")
                        new_lines.append('')
                        new_lines.append(indent + "location / {")
                        new_lines.append(indent + "    return 301 https://$host$request_uri;")
                        new_lines.append(indent + "}")
                        new_lines.append('}')
                        in_http_block = False
                        continue
            
            if not in_http_block:
                new_lines.append(line)
        
        if http_block_start >= 0 and http_block_end >= 0:
            new_content = '\n'.join(new_lines)
            print("✅ Replaced HTTP server block with ACME challenge")
        else:
            print("❌ Could not find HTTP server block")
            exit(1)
    
    with open(nginx_conf, 'w') as f:
        f.write(new_content)
    print("✅ Updated NGINX config with ACME challenge location")
PYTHON_EOF

# Create webroot directory for ACME challenge
mkdir -p /var/www/html/.well-known/acme-challenge
chmod -R 755 /var/www/html

# Reload NGINX to apply changes
if systemctl is-active --quiet nginx; then
    systemctl reload nginx || {
        echo "⚠️  NGINX reload failed. Please check configuration."
        nginx -t
    }
else
    echo "⚠️  NGINX is not running. Starting NGINX..."
    systemctl start nginx || {
        echo "❌ Failed to start NGINX"
        exit 1
    }
fi

# Request certificate using certbot
echo "🎫 Requesting Let's Encrypt certificate for $DOMAIN..."
echo "   Email: $EMAIL"
echo "   Validation method: webroot (HTTP-01)"

# Use certbot with webroot method (works with existing NGINX)
certbot certonly \
    --webroot \
    --webroot-path=/var/www/html \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN" \
    --non-interactive || {
    echo "❌ Certificate request failed"
    echo ""
    echo "Common issues:"
    echo "1. DNS not pointing to this server: Ensure $DOMAIN points to $(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'this server IP')"
    echo "2. Port 80 not accessible: Ensure security group allows inbound traffic on port 80"
    echo "3. NGINX not running: Check with 'systemctl status nginx'"
    exit 1
}

echo "✅ Certificate obtained successfully!"

# Update NGINX config to use Let's Encrypt certificates
CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
    echo "❌ Certificate files not found at expected paths"
    exit 1
fi

echo "🔧 Updating NGINX to use Let's Encrypt certificates..."

# Replace self-signed certificate paths with Let's Encrypt paths
sed -i "s|ssl_certificate /etc/nginx/ssl/selfsigned.crt;|ssl_certificate $CERT_PATH;|g" "$NGINX_CONF"
sed -i "s|ssl_certificate_key /etc/nginx/ssl/selfsigned.key;|ssl_certificate_key $KEY_PATH;|g" "$NGINX_CONF"

# Test NGINX configuration
if ! nginx -t; then
    echo "❌ NGINX configuration test failed"
    echo "Restoring backup..."
    cp "$BACKUP" "$NGINX_CONF"
    systemctl reload nginx
    exit 1
fi

# Reload NGINX to apply new certificate
systemctl reload nginx
echo "✅ NGINX reloaded with Let's Encrypt certificate"

# Set up auto-renewal
echo "🔄 Setting up automatic certificate renewal..."

# Create renewal hook script to reload NGINX after renewal
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# Test renewal process
echo "🧪 Testing certificate renewal..."
certbot renew --dry-run || {
    echo "⚠️  Renewal test failed, but certificate is installed"
}

# Add cron job for auto-renewal (certbot usually handles this, but ensure it exists)
if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
    (crontab -l 2>/dev/null; echo "0 0,12 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'") | crontab -
    echo "✅ Added cron job for certificate renewal"
fi

echo ""
echo "✅ Let's Encrypt certificate installation complete!"
echo ""
echo "📋 Summary:"
echo "   Domain: $DOMAIN"
echo "   Certificate: $CERT_PATH"
echo "   Private Key: $KEY_PATH"
echo "   Auto-renewal: Enabled (checks twice daily)"
echo ""
echo "🌐 Access your services:"
echo "   n8n: https://$DOMAIN"
echo "   Ollama API: https://$DOMAIN/api/ollama/"
echo "   Qdrant Dashboard: https://$DOMAIN/qdrant-ui/"
echo ""
echo "🔍 Verify certificate:"
echo "   openssl s_client -connect $DOMAIN:443 -servername $DOMAIN < /dev/null 2>/dev/null | openssl x509 -noout -dates"
echo ""
echo "📝 Next steps:"
echo "   1. Update DNS: Ensure $DOMAIN points to $(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'server IP')"
echo "   2. Test HTTPS: Visit https://$DOMAIN in your browser"
echo "   3. Certificate will auto-renew 30 days before expiration"
