#!/bin/bash
# Fix Qdrant UI NGINX configuration
# Run this script on the EC2 instance to update NGINX config

set -euo pipefail

NGINX_CONF="/etc/nginx/conf.d/default.conf"
BACKUP_CONF="${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"

echo "🔧 Fixing Qdrant UI NGINX configuration..."

# Backup existing config
if [ -f "$NGINX_CONF" ]; then
    echo "📋 Backing up existing config to $BACKUP_CONF"
    sudo cp "$NGINX_CONF" "$BACKUP_CONF"
else
    echo "❌ ERROR: NGINX config file not found at $NGINX_CONF"
    exit 1
fi

# Create temporary file with new qdrant-ui config
TEMP_FILE=$(mktemp)
cat > "$TEMP_FILE" << 'NGINX_CONFIG'
    # Qdrant Web UI (built-in dashboard)
    # Handle /qdrant-ui without trailing slash - redirect to /qdrant-ui/
    location = /qdrant-ui {
        return 301 $scheme://$host/qdrant-ui/;
    }

    # Qdrant Web UI - proxy to Qdrant dashboard
    location /qdrant-ui/ {
        rewrite ^/qdrant-ui/?(.*)$ /dashboard/$1 break;
        proxy_pass http://localhost:6333;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Qdrant dashboard timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
NGINX_CONFIG

# Find the old qdrant-ui location block and replace it
# First, find line numbers
START_LINE=$(sudo grep -n "# Qdrant Web UI" "$NGINX_CONF" | head -1 | cut -d: -f1)
if [ -z "$START_LINE" ]; then
    echo "❌ ERROR: Could not find Qdrant Web UI location block in config"
    exit 1
fi

# Find the end of the location block (next location or closing brace)
END_LINE=$(sudo awk -v start="$START_LINE" 'NR > start && /^[[:space:]]*location[[:space:]]/ {print NR-1; exit} NR > start && /^[[:space:]]*}[[:space:]]*$/ {if (NR > start + 5) {print NR; exit}}' "$NGINX_CONF")

if [ -z "$END_LINE" ]; then
    # Fallback: find next closing brace after start line
    END_LINE=$(sudo awk -v start="$START_LINE" 'NR > start && /^[[:space:]]*}[[:space:]]*$/ {print NR; exit}' "$NGINX_CONF")
fi

if [ -z "$END_LINE" ]; then
    echo "❌ ERROR: Could not determine end of Qdrant Web UI location block"
    exit 1
fi

echo "📍 Found Qdrant UI config block at lines $START_LINE-$END_LINE"

# Create new config file
sudo sed "${START_LINE},${END_LINE}d" "$NGINX_CONF" > "${TEMP_FILE}.new"

# Insert new config at the right location
sudo sed "${START_LINE}i\\
$(cat "$TEMP_FILE" | sed 's/$/\\/')
" "${TEMP_FILE}.new" > "${TEMP_FILE}.final"

# Replace original config
sudo mv "${TEMP_FILE}.final" "$NGINX_CONF"
sudo chmod 644 "$NGINX_CONF"

# Clean up temp files
rm -f "$TEMP_FILE" "${TEMP_FILE}.new"

# Test NGINX configuration
echo "🧪 Testing NGINX configuration..."
if sudo nginx -t; then
    echo "✅ NGINX configuration is valid"
    
    # Reload NGINX
    echo "🔄 Reloading NGINX..."
    if sudo systemctl reload nginx; then
        echo "✅ NGINX reloaded successfully"
        echo ""
        echo "🎉 Qdrant UI fix applied successfully!"
        echo "📝 Backup saved to: $BACKUP_CONF"
        echo "🌐 Test the dashboard at: https://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)/qdrant-ui/"
    else
        echo "❌ ERROR: Failed to reload NGINX"
        echo "🔄 Restoring backup..."
        sudo cp "$BACKUP_CONF" "$NGINX_CONF"
        sudo systemctl reload nginx
        exit 1
    fi
else
    echo "❌ ERROR: NGINX configuration test failed"
    echo "🔄 Restoring backup..."
    sudo cp "$BACKUP_CONF" "$NGINX_CONF"
    exit 1
fi
