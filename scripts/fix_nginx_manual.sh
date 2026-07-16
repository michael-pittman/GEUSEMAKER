#!/bin/bash
# Manual fix for NGINX config - properly insert ACME challenge
set -e

# Restore from backup
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
echo "Restoring from: $BACKUP"
cp "$BACKUP" /etc/nginx/conf.d/default.conf

# Update domain
sed -i "s/server_name _;/server_name ai.geuse.io;/g" /etc/nginx/conf.d/default.conf

# Update certificate paths
sed -i "s|ssl_certificate /etc/nginx/ssl/selfsigned.crt;|ssl_certificate /etc/letsencrypt/live/ai.geuse.io/fullchain.pem;|g" /etc/nginx/conf.d/default.conf
sed -i "s|ssl_certificate_key /etc/nginx/ssl/selfsigned.key;|ssl_certificate_key /etc/letsencrypt/live/ai.geuse.io/privkey.pem;|g" /etc/nginx/conf.d/default.conf

# Use awk to insert ACME challenge BEFORE location / in HTTP server block
awk '
/server {/ {
    in_server = 1
    brace_count = 0
    http_block = 0
}
in_server {
    if (/listen 80;/) {
        http_block = 1
    }
    if (http_block && /location \/ {/) {
        # Insert ACME challenge before location /
        print "    # Let'\''s Encrypt validation"
        print "    location /.well-known/acme-challenge/ {"
        print "        root /var/www/html;"
        print "        try_files $uri =404;"
        print "    }"
        print ""
    }
    print
    if (/{/) brace_count++
    if (/}/) {
        brace_count--
        if (brace_count == 0) {
            in_server = 0
            http_block = 0
        }
    }
    next
}
{ print }
' /etc/nginx/conf.d/default.conf > /tmp/nginx_fixed.conf

mv /tmp/nginx_fixed.conf /etc/nginx/conf.d/default.conf

# Test and reload
nginx -t
systemctl reload nginx
echo "✅ NGINX configured successfully with Let's Encrypt certificate"
