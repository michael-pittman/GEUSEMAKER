# Manual NGINX Fix for Qdrant UI

This guide shows how to manually fix the Qdrant UI NGINX configuration on your EC2 instance.

## Quick Fix (Automated Script)

1. **Copy the fix script to your EC2 instance:**
   ```bash
   scp -i ~/.ssh/your-key.pem scripts/fix_qdrant_ui_nginx.sh ec2-user@54.224.107.180:/tmp/
   ```

2. **SSH to your instance:**
   ```bash
   ssh -i ~/.ssh/your-key.pem ec2-user@54.224.107.180
   ```

3. **Run the fix script:**
   ```bash
   sudo bash /tmp/fix_qdrant_ui_nginx.sh
   ```

## Manual Fix (Step-by-Step)

If you prefer to do it manually:

1. **SSH to your instance:**
   ```bash
   ssh -i ~/.ssh/your-key.pem ec2-user@54.224.107.180
   ```

2. **Backup the current NGINX config:**
   ```bash
   sudo cp /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.backup
   ```

3. **Edit the NGINX config:**
   ```bash
   sudo nano /etc/nginx/conf.d/default.conf
   ```

4. **Find the Qdrant Web UI section** (around line 87-95) and **replace** it with:

   ```nginx
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
   ```

5. **Test the configuration:**
   ```bash
   sudo nginx -t
   ```

6. **If test passes, reload NGINX:**
   ```bash
   sudo systemctl reload nginx
   ```

7. **Verify Qdrant is running:**
   ```bash
   docker ps | grep qdrant
   ```

8. **Test the dashboard:**
   ```bash
   curl -k https://localhost/qdrant-ui/
   ```

## What Changed

- **Added redirect**: `/qdrant-ui` → `/qdrant-ui/` (handles missing trailing slash)
- **Improved rewrite**: Better regex pattern `^/qdrant-ui/?(.*)$` handles edge cases
- **Added timeouts**: Prevents premature disconnections

## Troubleshooting

If NGINX fails to reload:

1. **Restore backup:**
   ```bash
   sudo cp /etc/nginx/conf.d/default.conf.backup /etc/nginx/conf.d/default.conf
   sudo systemctl reload nginx
   ```

2. **Check NGINX error logs:**
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```

3. **Verify Qdrant is accessible:**
   ```bash
   curl http://localhost:6333/dashboard/
   ```

## Expected Result

After applying the fix, you should be able to access:
- `https://54.224.107.180/qdrant-ui/` ✅
- `https://54.224.107.180/qdrant-ui` ✅ (redirects to `/qdrant-ui/`)

Both should show the Qdrant Web UI dashboard.
