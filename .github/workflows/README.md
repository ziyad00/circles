# CI/CD Setup

This repository uses GitHub Actions for automated deployment to AWS ECS.

## Required GitHub Secrets

To set up the CI/CD pipeline, you need to configure the following secrets in your GitHub repository:

1. Go to your GitHub repository settings
2. Navigate to **Secrets and variables** > **Actions**
3. Add the following repository secrets:

- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key

## How it works

1. **Trigger**: The workflow runs on every push to the `main` branch
2. **Build**: Builds the Docker image from the Dockerfile
3. **Push**: Pushes the image to Amazon ECR
4. **Deploy**: Updates the ECS service with the new image
5. **Wait**: Waits for the service to reach a stable state

## Manual Deployment

If you need to deploy manually (current setup), you can:

1. Build and push to ECR:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 704845220483.dkr.ecr.us-east-1.amazonaws.com
   docker build -t circles-app .
   docker tag circles-app:latest 704845220483.dkr.ecr.us-east-1.amazonaws.com/circles-app:latest
   docker push 704845220483.dkr.ecr.us-east-1.amazonaws.com/circles-app:latest
   ```

2. Update ECS service to use the new image (done automatically via task definition updates)

## Monitoring

- Check GitHub Actions tab for deployment status
- Monitor ECS service in AWS console
- Check CloudWatch logs at `/ecs/circles` for application logs