# AWS CI/CD Pipeline Setup

This project now includes both GitHub Actions and AWS native CI/CD pipelines. The AWS native pipeline is recommended for better integration with your existing AWS infrastructure.

## AWS Native CI/CD Pipeline (Recommended)

### Architecture
- **CodePipeline**: Orchestrates the entire CI/CD process
- **CodeBuild**: Builds Docker images and deploys to ECS
- **CodeStar Connections**: Connects to GitHub repository
- **ECR**: Stores Docker images
- **ECS**: Runs the containerized application

### Setup Instructions

1. **Deploy the CI/CD infrastructure**:
   ```bash
   ./scripts/setup-cicd.sh
   ```

2. **Activate GitHub connection**:
   - Go to AWS Console > Developer Tools > Settings > Connections
   - Find the connection that was created
   - Click "Update pending connection"
   - Authorize with your GitHub account

3. **Verify pipeline**:
   ```bash
   aws codepipeline get-pipeline-state --name circles-pipeline --region us-east-1
   ```

### How it works
1. **Source**: Monitors your GitHub repository `main` branch
2. **Build**:
   - Builds Docker image from Dockerfile
   - Pushes to ECR
   - Updates ECS task definition
   - Deploys to ECS service
3. **Automatic**: Triggers on every push to `main`

### Monitoring
- **CodePipeline Console**: Monitor pipeline execution
- **CodeBuild Console**: View build logs and details
- **CloudWatch Logs**: Application logs at `/ecs/circles`
- **ECS Console**: Monitor service health and deployments

## GitHub Actions CI/CD (Alternative)

If you prefer GitHub Actions, the workflow is available at `.github/workflows/deploy.yml`.

### Setup for GitHub Actions:
1. Add repository secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

2. The workflow will run on every push to `main`

## Manual Deployment (Fallback)

For immediate deployments or troubleshooting:
```bash
./scripts/deploy.sh
```

## File Structure

```
├── buildspec.yml                    # CodeBuild build specification
├── .github/workflows/deploy.yml     # GitHub Actions workflow (optional)
├── infra/terraform/
│   ├── cicd.tf                     # CI/CD infrastructure
│   ├── main.tf                     # Main infrastructure
│   └── variables.tf                # Terraform variables
└── scripts/
    ├── deploy.sh                   # Manual deployment script
    └── setup-cicd.sh              # CI/CD setup script
```

## Benefits of AWS Native Pipeline

1. **Integration**: Seamless integration with existing AWS services
2. **Security**: Uses AWS IAM roles instead of storing credentials
3. **Cost**: No need for external CI/CD services for private repos
4. **Monitoring**: Native CloudWatch integration
5. **Scalability**: Automatically scales build capacity

## Troubleshooting

### Common Issues:
1. **Connection Pending**: Make sure to activate the GitHub connection in AWS Console
2. **Build Failures**: Check CodeBuild logs in AWS Console
3. **Deployment Failures**: Check ECS service events and CloudWatch logs
4. **Permission Issues**: Verify IAM roles have necessary permissions

### Useful Commands:
```bash
# Check pipeline status
aws codepipeline get-pipeline-state --name circles-pipeline

# Check build logs
aws logs tail /aws/codebuild/circles-build --follow

# Check application logs
aws logs tail /ecs/circles --follow

# Manual deployment
./scripts/deploy.sh
```

## Next Steps

1. Run `./scripts/setup-cicd.sh` to deploy the infrastructure
2. Activate the GitHub connection
3. Push a change to see the pipeline in action
4. Monitor via AWS Console

Your application will now automatically deploy whenever you push changes to the main branch! 🚀