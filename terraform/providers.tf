# terraform/providers.tf
terraform {
  required_version = "~> 1.6" # Pins a compatible Terraform version

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # Pins a compatible AWS provider version
    }
  }
}

# Configure the AWS Provider
# Credentials are loaded from AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY env vars
provider "aws" {
  region = "us-east-1" # Change this to your preferred region
}