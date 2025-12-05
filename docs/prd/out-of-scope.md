# Out of Scope

The following are explicitly **OUT OF SCOPE** for this version:

1. **Workflow Content Management**: System deploys n8n but does not create or manage workflows
2. **Model Management**: System deploys Ollama but users pull models manually
3. **Multi-Cloud Support**: AWS only (no Azure, GCP, on-premises)
4. **Custom Container Builds**: Uses official public images only
5. **Advanced Monitoring**: Basic health checks only (no custom dashboards, alerting beyond AWS native)
6. **Backup Automation**: Users responsible for backup strategies
7. **Service Configuration**: Uses default service configurations (users customize post-deployment)
8. **Auto-Scaling Policies**: Manual scaling or simple auto-scaling (no complex predictive scaling)
9. **Multi-Tenancy**: Single tenant per deployment
10. **Service Mesh**: No service mesh integration (Istio, App Mesh, etc.)

---
