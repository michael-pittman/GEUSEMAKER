#!/bin/bash
# Simple Let's Encrypt installation using certbot --nginx plugin
set -e

DOMAIN="${1:-ai.geuse.io}"
EMAIL="${2:-admin@geuse.io}"

echo "🔒 Installing Let's Encrypt certificate for $DOMAIN"

# Restore NGINX config from backup first
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
if [ -n "$BACKUP" ]; then
    echo "📋 Restoring NGINX config from backup"
    cp "$BACKUP" /etc/nginx/conf.d/default.conf
    # Update server_name to domain
    sed -i "s/server_name _;/server_name $DOMAIN;/g" /etc/nginx/conf.d/default.conf
    # Add ACME challenge location to HTTP server block
    sed -i '/listen 80;/,/location \/ {/ {
        /location \/ {/i\
    # Let'\''s Encrypt validation\
    location /.well-known/acme-challenge/ {\
        root /var/www/html;\
        try_files $uri =404;\
    }\
' /etc/nginx/conf.d/default.conf
    nginx -t && systemctl reload nginx
fi

# Create webroot
mkdir -p /var/www/html/.well-known/acme-challenge
chmod -R 755 /var/www/html

# Install certbot if needed
if ! command -v certbot >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y certbot python3-certbot-nginx
fi

# Request certificate using webroot method
echo "🎫 Requesting certificate..."
certbot certonly \
    --webroot \
    --webroot-path=/var/www/html \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN" \
    --non-interactive

# Update NGINX to use Let's Encrypt certs
CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

if [ -f "$CERT_PATH" ] && [ -f "$KEY_PATH" ]; then
    sed -i "s|ssl_certificate /etc/nginx/ssl/selfsigned.crt;|ssl_certificate $CERT_PATH;|g" /etc/nginx/conf.d/default.conf
    sed -i "s|ssl_certificate_key /etc/nginx/ssl/selfsigned.key;|ssl_certificate_key $KEY_PATH;|g" /etc/nginx/conf.d/default.conf
    nginx -t && systemctl reload nginx
    echo "✅ Certificate installed and NGINX updated"
else
    echo "❌ Certificate files not found"
    exit 1
fi

# Setup auto-renewal
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

echo "✅ Installation complete! Access https://$DOMAIN"
