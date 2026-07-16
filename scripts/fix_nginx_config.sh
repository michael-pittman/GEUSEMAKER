#!/bin/bash
# Fix NGINX config - restore clean HTTP server block with ACME challenge

set -e

NGINX_CONF="/etc/nginx/conf.d/default.conf"
DOMAIN="${1:-ai.geuse.io}"

echo "🔧 Fixing NGINX configuration for $DOMAIN"

# Restore from most recent backup
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
if [ -n "$BACKUP" ]; then
    echo "📋 Restoring from backup: $BACKUP"
    cp "$BACKUP" "$NGINX_CONF"
else
    echo "⚠️  No backup found, working with current config"
fi

# Use Python to cleanly replace HTTP server block
python3 << PYEOF
nginx_conf = "/etc/nginx/conf.d/default.conf"
domain = "$DOMAIN"

with open(nginx_conf, 'r') as f:
    content = f.read()

# Find and replace HTTP server block completely
import re

# Pattern: HTTP server block from "server {" to closing "}"
# Match everything between server { with listen 80 and the matching closing brace
lines = content.split('\n')
new_lines = []
i = 0
in_http_block = False
http_start = -1
brace_depth = 0

while i < len(lines):
    line = lines[i]
    
    # Detect start of HTTP server block
    if 'server {' in line:
        # Check if next lines contain listen 80
        lookahead = '\n'.join(lines[i:min(i+10, len(lines))])
        if 'listen 80;' in lookahead:
            in_http_block = True
            http_start = len(new_lines)
            # Add clean HTTP server block
            new_lines.append('server {')
            new_lines.append('    listen 80;')
            new_lines.append('    listen [::]:80;')
            new_lines.append(f'    server_name {domain};')
            new_lines.append('')
            new_lines.append('    # Let'\''s Encrypt validation')
            new_lines.append('    location /.well-known/acme-challenge/ {')
            new_lines.append('        root /var/www/html;')
            new_lines.append('        try_files $uri =404;')
            new_lines.append('    }')
            new_lines.append('')
            new_lines.append('    location / {')
            new_lines.append('        return 301 https://$host$request_uri;')
            new_lines.append('    }')
            new_lines.append('}')
            # Skip original HTTP block lines
            brace_depth = 1
            i += 1
            while i < len(lines) and brace_depth > 0:
                if '{' in lines[i]:
                    brace_depth += lines[i].count('{')
                if '}' in lines[i]:
                    brace_depth -= lines[i].count('}')
                i += 1
            continue
    
    new_lines.append(line)
    i += 1

# Write back
with open(nginx_conf, 'w') as f:
    f.write('\n'.join(new_lines))

print("✅ NGINX config fixed")
PYEOF

# Test config
if nginx -t; then
    echo "✅ NGINX config is valid"
    systemctl reload nginx
    echo "✅ NGINX reloaded successfully"
else
    echo "❌ NGINX config test failed"
    nginx -t
    exit 1
fi
