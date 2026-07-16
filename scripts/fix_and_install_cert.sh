#!/bin/bash
# Complete fix and certificate installation script
set -e

DOMAIN="ai.geuse.io"
EMAIL="admin@geuse.io"

echo "🔧 Step 1: Restoring and fixing NGINX config"

# Restore from backup
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
if [ -n "$BACKUP" ]; then
    cp "$BACKUP" /etc/nginx/conf.d/default.conf
    echo "✅ Restored from backup"
fi

# Create clean HTTP server block with Python
python3 << 'PYEOF'
nginx_conf = "/etc/nginx/conf.d/default.conf"
domain = "ai.geuse.io"

with open(nginx_conf, 'r') as f:
    lines = f.readlines()

# Find HTTP server block and replace it completely
new_lines = []
i = 0
in_http = False
http_start = -1
depth = 0

while i < len(lines):
    line = lines[i]
    
    # Detect HTTP server block start
    if 'server {' in line:
        lookahead = '\n'.join(lines[i:min(i+10, len(lines))])
        if 'listen 80;' in lookahead:
            in_http = True
            http_start = len(new_lines)
            # Add clean HTTP block
            new_lines.append('server {\n')
            new_lines.append('    listen 80;\n')
            new_lines.append('    listen [::]:80;\n')
            new_lines.append(f'    server_name {domain};\n')
            new_lines.append('\n')
            new_lines.append('    # Let'\''s Encrypt validation\n')
            new_lines.append('    location /.well-known/acme-challenge/ {\n')
            new_lines.append('        root /var/www/html;\n')
            new_lines.append('        try_files $uri =404;\n')
            new_lines.append('    }\n')
            new_lines.append('\n')
            new_lines.append('    location / {\n')
            new_lines.append('        return 301 https://$host$request_uri;\n')
            new_lines.append('    }\n')
            new_lines.append('}\n')
            # Skip original HTTP block
            depth = 1
            i += 1
            while i < len(lines) and depth > 0:
                if '{' in lines[i]:
                    depth += lines[i].count('{')
                if '}' in lines[i]:
                    depth -= lines[i].count('}')
                i += 1
            continue
    
    new_lines.append(line)
    i += 1

with open(nginx_conf, 'w') as f:
    f.writelines(new_lines)

print("✅ NGINX config fixed")
PYEOF

# Test and reload NGINX
nginx -t
systemctl reload nginx
echo "✅ NGINX reloaded"

# Create webroot
mkdir -p /var/www/html/.well-known/acme-challenge
chmod -R 755 /var/www/html

echo ""
echo "🎫 Step 2: Requesting Let's Encrypt certificate"

# Request certificate
certbot certonly \
    --webroot \
    --webroot-path=/var/www/html \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN" \
    --non-interactive

echo "✅ Certificate obtained"

# Update NGINX to use Let's Encrypt certs
CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

sed -i "s|ssl_certificate /etc/nginx/ssl/selfsigned.crt;|ssl_certificate $CERT_PATH;|g" /etc/nginx/conf.d/default.conf
sed -i "s|ssl_certificate_key /etc/nginx/ssl/selfsigned.key;|ssl_certificate_key $KEY_PATH;|g" /etc/nginx/conf.d/default.conf

nginx -t
systemctl reload nginx

# Setup auto-renewal
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo ""
echo "✅ Installation complete!"
echo "🌐 Access: https://$DOMAIN"
