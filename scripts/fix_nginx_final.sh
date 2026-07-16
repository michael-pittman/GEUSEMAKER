#!/bin/bash
set -e

# Restore from backup
BACKUP=$(ls -t /etc/nginx/conf.d/default.conf.backup.* 2>/dev/null | head -1)
if [ -n "$BACKUP" ]; then
    cp "$BACKUP" /etc/nginx/conf.d/default.conf
fi

# Update server name and certificate paths
sed -i "s/server_name _;/server_name ai.geuse.io;/g" /etc/nginx/conf.d/default.conf
sed -i "s|ssl_certificate /etc/nginx/ssl/selfsigned.crt;|ssl_certificate /etc/letsencrypt/live/ai.geuse.io/fullchain.pem;|g" /etc/nginx/conf.d/default.conf
sed -i "s|ssl_certificate_key /etc/nginx/ssl/selfsigned.key;|ssl_certificate_key /etc/letsencrypt/live/ai.geuse.io/privkey.pem;|g" /etc/nginx/conf.d/default.conf

# Use Python to properly insert ACME challenge
python3 << 'PYEOF'
with open("/etc/nginx/conf.d/default.conf", "r") as f:
    lines = f.readlines()

new_lines = []
i = 0
in_http_block = False
http_block_start = -1
brace_depth = 0

while i < len(lines):
    line = lines[i]
    
    # Detect HTTP server block start
    if "server {" in line:
        # Look ahead to see if this is HTTP block
        lookahead = "".join(lines[i:min(i+10, len(lines))])
        if "listen 80;" in lookahead:
            in_http_block = True
            http_block_start = len(new_lines)
            new_lines.append(line)
            i += 1
            brace_depth = 1
            
            # Copy lines until we find "location / {"
            while i < len(lines) and brace_depth > 0:
                if "location / {" in lines[i]:
                    # Insert ACME challenge before location /
                    new_lines.append("    # Let's Encrypt validation\n")
                    new_lines.append("    location /.well-known/acme-challenge/ {\n")
                    new_lines.append("        root /var/www/html;\n")
                    new_lines.append("        try_files $uri =404;\n")
                    new_lines.append("    }\n")
                    new_lines.append("\n")
                    # Now add location /
                    new_lines.append(lines[i])
                    i += 1
                    break
                else:
                    new_lines.append(lines[i])
                    if "{" in lines[i]:
                        brace_depth += lines[i].count("{")
                    if "}" in lines[i]:
                        brace_depth -= lines[i].count("}")
                    i += 1
            
            # Copy rest of HTTP block
            while i < len(lines) and brace_depth > 0:
                new_lines.append(lines[i])
                if "{" in lines[i]:
                    brace_depth += lines[i].count("{")
                if "}" in lines[i]:
                    brace_depth -= lines[i].count("}")
                i += 1
            in_http_block = False
            continue
    
    new_lines.append(line)
    i += 1

with open("/etc/nginx/conf.d/default.conf", "w") as f:
    f.writelines(new_lines)
PYEOF

# Test and reload
nginx -t
systemctl reload nginx
echo "✅ NGINX configured successfully with Let's Encrypt certificate"
