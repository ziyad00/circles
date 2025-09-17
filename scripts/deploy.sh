#!/bin/bash

# Deploy script for circles app
# This script builds and deploys the application to AWS ECS

set -e

AWS_REGION="us-east-1"
ECR_REPOSITORY="circles-app"
ECS_SERVICE="circles-svc"
ECS_CLUSTER="circles-cluster"
ECS_TASK_DEFINITION="circles-task"

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --region ${AWS_REGION} --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "🚀 Starting deployment..."
echo "Registry: ${ECR_REGISTRY}"
echo "Repository: ${ECR_REPOSITORY}"

# Login to ECR
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}

# Build image
echo "🏗️  Building Docker image..."
docker build -t ${ECR_REPOSITORY}:latest .

# Tag image
echo "🏷️  Tagging image..."
docker tag ${ECR_REPOSITORY}:latest ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest

# Push image
echo "📤 Pushing image to ECR..."
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest

# Get the image digest
IMAGE_DIGEST=$(aws ecr describe-images --repository-name ${ECR_REPOSITORY} --region ${AWS_REGION} --query 'imageDetails[0].imageDigest' --output text)
NEW_IMAGE="${ECR_REGISTRY}/${ECR_REPOSITORY}@${IMAGE_DIGEST}"

echo "📋 Updating ECS task definition..."
# Download current task definition
aws ecs describe-task-definition --task-definition ${ECS_TASK_DEFINITION} --region ${AWS_REGION} --query taskDefinition > task-definition.json

# Update the image in task definition
export NEW_IMAGE
python3 << 'EOF'
import json
import sys
import os

# Read the task definition
with open('task-definition.json', 'r') as f:
    task_def = json.load(f)

# Remove fields that are not needed for registration
for key in ['taskDefinitionArn', 'revision', 'status', 'requiresAttributes', 'placementConstraints', 'compatibilities', 'registeredAt', 'registeredBy']:
    task_def.pop(key, None)

# Update the image using environment variable
new_image = os.environ.get('NEW_IMAGE')
if new_image:
    task_def['containerDefinitions'][0]['image'] = new_image

# Write back
with open('task-definition.json', 'w') as f:
    json.dump(task_def, f, indent=2)
EOF

# Register new task definition
echo "📝 Registering new task definition..."
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition --cli-input-json file://task-definition.json --region ${AWS_REGION} --query 'taskDefinition.taskDefinitionArn' --output text)

# Update the service
echo "🔄 Updating ECS service..."
aws ecs update-service --cluster ${ECS_CLUSTER} --service ${ECS_SERVICE} --task-definition ${NEW_TASK_DEF_ARN} --region ${AWS_REGION}

# Wait for deployment to complete
echo "⏳ Waiting for service to stabilize..."
aws ecs wait services-stable --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --region ${AWS_REGION}

# Clean up
rm -f task-definition.json

echo "✅ Deployment completed successfully!"
echo "🔗 Check your application at: http://circles-alb-1949181177.us-east-1.elb.amazonaws.com"