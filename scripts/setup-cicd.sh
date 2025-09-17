#!/bin/bash

# Setup script for AWS CI/CD pipeline
# This script initializes and applies the CI/CD infrastructure

set -e

echo "🚀 Setting up AWS CI/CD pipeline..."

# Change to terraform directory
cd "$(dirname "$0")/../infra/terraform"

# Check if terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform is not installed. Please install Terraform first."
    exit 1
fi

# Initialize terraform if not already done
if [ ! -d ".terraform" ]; then
    echo "🔧 Initializing Terraform..."
    terraform init
fi

# Plan the changes
echo "📋 Planning Terraform changes..."
terraform plan -out=tfplan

# Apply the changes
echo "🚀 Applying Terraform changes..."
terraform apply tfplan

# Get outputs
echo "📊 Getting important outputs..."
CODEPIPELINE_NAME=$(terraform output -raw codepipeline_name)
GITHUB_CONNECTION_ARN=$(terraform output -raw github_connection_arn)

echo ""
echo "✅ CI/CD pipeline setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Activate the GitHub connection:"
echo "   - Go to AWS Console > Developer Tools > Settings > Connections"
echo "   - Find connection: $GITHUB_CONNECTION_ARN"
echo "   - Click 'Update pending connection' and authorize with GitHub"
echo ""
echo "2. Monitor pipeline:"
echo "   - CodePipeline: $CODEPIPELINE_NAME"
echo "   - The pipeline will automatically trigger on pushes to main branch"
echo ""
echo "3. Check pipeline status:"
echo "   aws codepipeline get-pipeline-state --name $CODEPIPELINE_NAME --region us-east-1"
echo ""
echo "🎉 Your application will now automatically deploy when you push to GitHub!"

# Clean up
rm -f tfplan