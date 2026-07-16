#!/bin/bash
# Fix NGINX config to add ACME challenge location in HTTP server block

NGINX_CONF="/etc/nginx/conf.d/default.conf"

# Restore from backup if exists
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
if [ -n "$BACKUP" ]; then
    echo "Restoring from backup: $BACKUP"
    cp "$BACKUP" "$NGINX_CONF"
fi

# Use a simple sed approach: find HTTP server block and add ACME challenge before location /
# The HTTP server block starts with "server {" and has "listen 80"
# We need to add the ACME challenge location BEFORE the "location /" that redirects

python3 << 'PYEOF'
nginx_conf = "/etc/nginx/conf.d/default.conf"

with open(nginx_conf, 'r') as f:
    content = f.read()

# Split into lines for easier manipulation
lines = content.split('\n')
new_lines = []
in_http_block = False
acme_added = False
i = 0

while i < len(lines):
    line = lines[i]
    
    # Detect HTTP server block start
    if 'server {' in line:
        # Check if next few lines contain "listen 80"
        lookahead = '\n'.join(lines[i:min(i+5, len(lines))])
        if 'listen 80;' in lookahead:
            in_http_block = True
    
    # If we're in HTTP block and see "location /" with redirect, add ACME challenge before it
    if in_http_block and 'location / {' in line and not acme_added:
        # Check if this location redirects
        next_few = '\n'.join(lines[i:min(i+5, len(lines))])
        if 'return 301 https:' in next_few:
            # Add ACME challenge location before this
            indent = '    '
            new_lines.append(f'{indent}# Let'\''s Encrypt validation')
            new_lines.append(f'{indent}location /.well-known/acme-challenge/ {{')
            new_lines.append(f'{indent}    root /var/www/html;')
            new_lines.append(f'{indent}    try_files $uri =404;')
            new_lines.append(f'{indent}}}')
            new_lines.append('')
            acme_added = True
    
    new_lines.append(line)
    
    # Detect end of HTTP server block
    if in_http_block and line.strip() == '}' and i > 0:
        # Check if we're closing the HTTP server block (not a location block)
        # Count braces to determine if we're at server level
        brace_count = 0
        for j in range(i, -1, -1):
            if lines[j].strip() == '}':
                brace_count += 1
            elif 'server {' in lines[j]:
                brace_count -= 1
                if brace_count == 0:
                    in_http_block = False
                    break
    
    i += 1

# Write back
with open(nginx_conf, 'w') as f:
    f.write('\n'.join(new_lines))

print("✅ NGINX config updated")
PYEOF

# Test NGINX config
if nginx -t; then
    echo "✅ NGINX config is valid"
    systemctl reload nginx
    echo "✅ NGINX reloaded"
else
    echo "❌ NGINX config test failed"
    exit 1
fi
