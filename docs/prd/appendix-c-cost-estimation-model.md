# Appendix C: Cost Estimation Model

Cost estimation must include these components:

1. **Compute Costs**:
   - EC2 instance hourly cost (spot or on-demand)
   - Number of instances × hourly rate
   - Consider spot interruption rates

2. **Storage Costs**:
   - EBS volume costs (GB × hourly rate)
   - EFS costs (GB × hourly rate) if applicable
   - Snapshot costs if backup enabled

3. **Network Costs**:
   - Data transfer out (estimated based on tier)
   - NAT Gateway hourly costs
   - Load Balancer hourly costs (if applicable)

4. **Additional Services**:
   - CloudFront costs (if CDN enabled)
   - CloudWatch costs (metrics, logs)

**Display Format**:
- Show hourly cost estimate
- Show daily cost estimate (24 hours)
- Show monthly cost estimate (730 hours)
- Break down by component
- Compare spot vs. on-demand savings

---
