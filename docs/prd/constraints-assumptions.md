# Constraints & Assumptions

## Constraints
- Must work with standard AWS account permissions (no organization admin required)
- Must operate within AWS service quotas and limits
- Must support AWS regions where all required services are available
- Must handle AWS API rate limits gracefully
- Must use latest stable versions of all tools and dependencies
- Internet connectivity required for AWS API access and service image downloads

## Assumptions
- Users have AWS account with EC2, VPC, and IAM permissions
- Users have AWS CLI configured or equivalent credentials available
- Users have basic understanding of AWS concepts (VPC, EC2, security groups)
- Service container images are publicly accessible (Docker Hub, etc.)
- Users accept AWS costs for deployed resources
- Users are responsible for securing service credentials post-deployment

---
