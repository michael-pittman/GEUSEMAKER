# Epic 14: ComfyUI Integration for LTX-2 Video Generation

## Epic Goal

Integrate ComfyUI service with LTX-2 custom nodes for video generation workflows in GPU deployments, enabling advanced AI video generation capabilities within the GeuseMaker stack.

## Epic Description

**Context:**
ComfyUI is a powerful node-based interface for Stable Diffusion and other AI models. The latest stable version is V1 (released October 21, 2024). Lightricks' LTX-2 is an open-source video generation model designed to work with ComfyUI. This epic adds ComfyUI as a service to the GeuseMaker stack, enabling users to run LTX-2 video generation workflows on GPU instances. ComfyUI requires GPU support and will be available only for GPU tier deployments. ComfyUI operates as a web server with HTTP REST APIs and WebSocket connections for real-time communication, making it ideal for integration with n8n workflows via HTTP Request nodes.

**Requirements from PRD:**
- Section 2: Deployment Tiers - Tier 3: GPU-Optimized
- Section 4: Service Specifications - Additional AI services
- Section 6.1: Deployment Creation (Service integration)

**Success Criteria:**
- ComfyUI container is deployed and accessible
- LTX-2 custom nodes are installed and available
- ComfyUI is accessible via NGINX reverse proxy
- Health checks verify ComfyUI service status
- EFS volumes persist ComfyUI models and outputs
- GPU instances support ComfyUI workloads
- Deployment state includes ComfyUI endpoint information

## Stories

1. **Story 14.1:** ComfyUI Service Integration
   - Add ComfyUI container to Docker Compose configuration
   - Use official ComfyUI Docker image (latest stable: V1) or build from source
   - Configure EFS volumes for models (`/app/models`), outputs (`/app/output`), inputs (`/app/input`), and custom nodes (`/app/custom_nodes`)
   - Add `comfyui_port` field to UserDataConfig model (default: 8188)
   - Update services template to include ComfyUI service definition
   - Configure NVIDIA GPU runtime for ComfyUI container (GPU tier only)
   - Set environment variables: `NVIDIA_VISIBLE_DEVICES=all` for GPU access
   - Add ComfyUI to container startup wait list
   - Update runtime.env template with COMFYUI_PORT variable
   - Ensure ComfyUI runs on port 8188 (default) with host binding

2. **Story 14.2:** ComfyUI Health Checks and Monitoring
   - Add `check_comfyui()` function to health service
   - Integrate ComfyUI health check into default health check configs
   - Update `check_all_services()` to include ComfyUI
   - Add ComfyUI health status to status command output
   - Configure health check endpoint (HTTP GET to `/`)
   - Add ComfyUI to post-deployment health validation

3. **Story 14.3:** LTX-2 Custom Nodes Setup
   - Create ComfyUI setup script template (`comfyui-setup.sh.j2`)
   - Install ComfyUI Manager via git clone: `cd /app/custom_nodes && git clone https://github.com/ltdrdata/ComfyUI-Manager comfyui-manager`
   - Install LTX-2 custom node pack: `cd /app/custom_nodes && git clone https://github.com/Lightricks/ComfyUI-LTXVideo.git`
   - Configure setup script to run only for GPU tier deployments
   - Wait for ComfyUI container to be ready before installing nodes
   - Add ComfyUI setup to UserData generation pipeline (after services start)
   - Handle setup failures gracefully with logging to `/var/log/geusemaker/comfyui-setup.log`
   - Restart ComfyUI container after custom node installation to load new nodes
   - Verify custom nodes are available via ComfyUI API after restart

4. **Story 14.4:** NGINX Proxy Configuration for ComfyUI
   - Add ComfyUI reverse proxy location block to NGINX config (`/comfyui/` path)
   - Configure WebSocket support for real-time ComfyUI updates (required for workflow execution)
   - Set extended timeouts for video generation: `proxy_connect_timeout 60s`, `proxy_send_timeout 1800s`, `proxy_read_timeout 1800s` (30 minutes)
   - Increase client body size limit for model uploads: `client_max_body_size 10G`
   - Configure proxy headers (Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto)
   - Proxy to `http://localhost:8188` (ComfyUI default port)
   - Add ComfyUI endpoint to deployment inspection output
   - Document ComfyUI access URL in deployment info (`https://<instance-ip>/comfyui/`)
   - Ensure WebSocket upgrade headers are properly configured for ComfyUI's real-time features

## Dependencies

- Requires: Epic 4 (Deployment Lifecycle Core) - needs base deployment infrastructure
- Requires: Epic 13 (Tier 3 GPU/CloudFront) - ComfyUI/LTX-2 requires GPU instances
- Blocks: None (enhancement feature)

## Definition of Done

- [ ] ComfyUI container is deployed and running (latest stable version V1)
- [ ] LTX-2 custom nodes are installed and available in ComfyUI interface
- [ ] ComfyUI Manager is installed and functional
- [ ] ComfyUI is accessible via NGINX reverse proxy at `/comfyui/`
- [ ] WebSocket connections work correctly for real-time workflow updates
- [ ] Health checks verify ComfyUI service status (HTTP GET to `/`)
- [ ] EFS volumes persist ComfyUI data (models, outputs, custom nodes, inputs)
- [ ] GPU instances support ComfyUI workloads correctly (NVIDIA runtime configured)
- [ ] Deployment state includes ComfyUI endpoint information
- [ ] n8n can call ComfyUI API via HTTP Request node (internal Docker network: `http://comfyui:8188`)
- [ ] Long-running video generation requests are handled correctly (30+ minute timeouts)
- [ ] Unit and integration tests with 80%+ coverage
- [ ] Documentation updated with ComfyUI usage instructions and n8n integration examples

## n8n Integration Best Practices

**Internal Communication:**
- n8n workflows should call ComfyUI using Docker container hostname: `http://comfyui:8188`
- Use HTTP Request node in n8n to call ComfyUI API endpoints (`/prompt`, `/queue`, `/history`, etc.)
- For webhook callbacks, configure ComfyUI to call n8n webhook URLs

**API Endpoints:**
- `/prompt` - Submit workflow for execution
- `/queue` - Check queue status
- `/history` - Retrieve execution history
- `/view` - View generated outputs
- WebSocket: `/ws` - Real-time workflow updates

**Error Handling:**
- Implement retry logic for transient failures
- Handle long-running requests with appropriate timeouts
- Use n8n's error handling nodes for failed ComfyUI requests
