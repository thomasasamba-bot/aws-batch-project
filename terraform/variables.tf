# terraform/variables.tf
variable "project_name" {
  description = "Name of the project, used for resource naming and tagging."
  type        = string
  default     = "aws-batch-auditor"
}

variable "region" {
  description = "The AWS region where resources will be created."
  type        = string
  default     = "us-east-1"
}

variable "s3_audit_bucket_name" {
  description = "The name of the S3 bucket where audit reports will be stored. Must be globally unique."
  type        = string
}

variable "batch_job_memory" {
  description = "The memory allocation (in MB) for the Fargate batch job."
  type        = number
  default     = 2048
}

variable "batch_job_vcpus" {
  description = "The CPU allocation (in vCPUs) for the Fargate batch job."
  type        = number
  default     = 1
}

variable "oidc_role_name" {
  description = "Name of the existing OIDC IAM role for AWS Batch"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where resources will be deployed"
  type        = string
}

variable "subnet_ids" {
  description = "List of existing subnet IDs"
  type        = list(string)
}

variable "use_existing_subnets" {
  description = "Whether to use existing subnets or create new ones"
  type        = bool
  default     = false
}