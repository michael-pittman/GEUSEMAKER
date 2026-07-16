#!/bin/bash
# Complete certificate installation - fixes NGINX and installs cert
set -e

DOMAIN="ai.geuse.io"
EMAIL="admin@geuse.io"

echo "🔧 Fixing NGINX configuration..."

# Restore from backup
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
if [ -n "$BACKUP" ]; then
    cp "$BACKUP" /etc/nginx/conf.d/default.conf
fi

# Remove ALL existing ACME challenge locations (they might be in wrong places)
sed -i '/\.well-known\/acme-challenge/d' /etc/nginx/conf.d/default.conf
sed -i '/Let'\''s Encrypt validation/d' /etc/nginx/conf.d/default.conf

# Use awk to properly insert ACME challenge in HTTP server block only
awk '
/server {/ {
    in_server = 1
    server_lines = ""
    brace_count = 0
}
in_server {
    server_lines = server_lines $0 "\n"
    brace_count += gsub(/{/, "&")
    brace_count -= gsub(/}/, "&")
    
    # Check if this is HTTP server block
    if (/listen 80;/ && !http_found) {
        is_http = 1
        http_found = 1
    }
    
    # End of server block
    if (brace_count == 0 && in_server) {
        if (is_http) {
            # Replace HTTP server block with clean version
            print "server {"
            print "    listen 80;"
            print "    listen [::]:80;"
            print "    server_name " DOMAIN ";"
            print ""
            print "    # Let'\''s Encrypt validation"
            print "    location /.well-known/acme-challenge/ {"
            print "        root /var/www/html;"
            print "        try_files $uri =404;"
            print "    }"
            print ""
            print "    location / {"
            print "        return 301 https://$host$request_uri;"
            print "    }"
            print "}"
        } else {
            # Print HTTPS server block as-is
            printf "%s", server_lines
        }
        in_server = 0
        is_http = 0
        server_lines = ""
        next
    }
    next
}
{ print }
' DOMAIN="$DOMAIN" /etc/nginx/conf.d/default.conf > /tmp/nginx_fixed.conf

mv /tmp/nginx_fixed.conf /etc/nginx/conf.d/default.conf

# Test config
if nginx -t; then
    systemctl reload nginx
    echo "✅ NGINX config fixed and reloaded"
else
    echo "❌ NGINX config test failed"
    nginx -t
    exit 1
fi

# Create webroot
mkdir -p /var/www/html/.well-known/acme-challenge
chmod -R 755 /var/www/html

echo ""
echo "🎫 Requesting Let's Encrypt certificate..."

certbot certonly \
    --webroot \
    --webroot-path=/var/www/html \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --domains "$DOMAIN" \
    --non-interactive

CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

if [ -f "$CERT_PATH" ] && [ -f "$KEY_PATH" ]; then
    sed -i "s|ssl_certificate /etc/nginx/ssl/selfsigned.crt;|ssl_certificate $CERT_PATH;|g" /etc/nginx/conf.d/default.conf
    sed -i "s|ssl_certificate_key /etc/nginx/ssl/selfsigned.key;|ssl_certificate_key $KEY_PATH;|g" /etc/nginx/conf.d/default.conf
    
    nginx -t && systemctl reload nginx
    
    # Setup auto-renewal
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
    chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    
    echo ""
    echo "✅ Certificate installation complete!"
    echo "🌐 Access: https://$DOMAIN"
else
    echo "❌ Certificate files not found"
    exit 1
fi
