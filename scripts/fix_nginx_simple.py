#!/usr/bin/env python3
"""Simple Python script to fix NGINX config."""
import re

nginx_conf = "/etc/nginx/conf.d/default.conf"

with open(nginx_conf, 'r') as f:
    content = f.read()

# Find and replace the entire HTTP server block
http_block_pattern = r'server \{[^}]*listen 80;[^}]*listen \[::\]:80;[^}]*server_name[^}]*;[^}]*location / \{[^}]*return 301[^}]*\}[^}]*\}'

http_block_replacement = """server {
    listen 80;
    listen [::]:80;
    server_name ai.geuse.io;

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/html;
        try_files $uri =404;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}"""

# Try to replace HTTP block
new_content = re.sub(http_block_pattern, http_block_replacement, content, flags=re.DOTALL)

# If replacement didn't work, do line-by-line replacement
if new_content == content:
    lines = content.split('\n')
    new_lines = []
    i = 0
    in_http = False
    http_start = -1
    brace_depth = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Detect HTTP server block start
        if 'server {' in line:
            lookahead = '\n'.join(lines[i:min(i+10, len(lines))])
            if 'listen 80;' in lookahead:
                in_http = True
                # Add clean HTTP block
                new_lines.append('server {')
                new_lines.append('    listen 80;')
                new_lines.append('    listen [::]:80;')
                new_lines.append('    server_name ai.geuse.io;')
                new_lines.append('')
                new_lines.append('    # Let\'s Encrypt validation')
                new_lines.append('    location /.well-known/acme-challenge/ {')
                new_lines.append('        root /var/www/html;')
                new_lines.append('        try_files $uri =404;')
                new_lines.append('    }')
                new_lines.append('')
                new_lines.append('    location / {')
                new_lines.append('        return 301 https://$host$request_uri;')
                new_lines.append('    }')
                new_lines.append('}')
                # Skip original HTTP block
                brace_depth = 1
                i += 1
                while i < len(lines) and brace_depth > 0:
                    if '{' in lines[i]:
                        brace_depth += lines[i].count('{')
                    if '}' in lines[i]:
                        brace_depth -= lines[i].count('}')
                    i += 1
                in_http = False
                continue
        
        new_lines.append(line)
        i += 1
    
    new_content = '\n'.join(new_lines)

# Update certificate paths
new_content = re.sub(
    r'ssl_certificate /etc/nginx/ssl/selfsigned\.crt;',
    'ssl_certificate /etc/letsencrypt/live/ai.geuse.io/fullchain.pem;',
    new_content
)
new_content = re.sub(
    r'ssl_certificate_key /etc/nginx/ssl/selfsigned\.key;',
    'ssl_certificate_key /etc/letsencrypt/live/ai.geuse.io/privkey.pem;',
    new_content
)

# Update server_name
new_content = re.sub(
    r'server_name _;',
    'server_name ai.geuse.io;',
    new_content
)

with open(nginx_conf, 'w') as f:
    f.write(new_content)

print("✅ NGINX config fixed")
