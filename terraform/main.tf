# terraform/main.tf

# Get the default VPC
data "aws_vpc" "default" {
  default = true
}

# Get available subnets in the default VPC
data "aws_subnets" "available" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Create a security group for the Batch jobs
resource "aws_security_group" "batch_sg" {
  name        = "${var.project_name}-batch-sg"
  description = "Security group for AWS Batch jobs"
  vpc_id      = data.aws_vpc.default.id

  # Allow outbound traffic to anywhere (required for Batch jobs)
  ingress {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = var.project_name
  }
}

# Create an S3 bucket for our audit reports
resource "aws_s3_bucket" "audit_reports" {
  bucket = var.s3_audit_bucket_name

  tags = {
    Name        = var.project_name
    Environment = "Dev"
    Project     = var.project_name
  }
}

# Optional: Configure the S3 bucket to avoid accidental deletion (good practice)
resource "aws_s3_bucket_ownership_controls" "audit_reports" {
  bucket = aws_s3_bucket.audit_reports.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "audit_reports" {
  depends_on = [aws_s3_bucket_ownership_controls.audit_reports]
  bucket     = aws_s3_bucket.audit_reports.id
  acl        = "private"
}

# Create an ECR repository to store our Docker image
resource "aws_ecr_repository" "batch_job_repo" {
  name = "${var.project_name}-repo"

  image_scanning_configuration {
    scan_on_push = true # Enable scanning for vulnerabilities
  }

  tags = {
    Project = var.project_name
  }
}

# Get existing OIDC IAM role (instead of creating one)
data "aws_iam_role" "oidc_role" {
  name = var.oidc_role_name
}

# Create the AWS Batch Compute Environment (Fargate)
resource "aws_batch_compute_environment" "fargate_env" {
  compute_environment_name = "${var.project_name}-fargate-env"
  type                     = "MANAGED"
  state                    = "ENABLED"
  service_role             = data.aws_iam_role.oidc_role.arn

  compute_resources {
    type       = "FARGATE"
    max_vcpus  = 4
    
    # Use the subnets and security group we created
    subnets            = data.aws_subnets.available.ids
    security_group_ids = [aws_security_group.batch_sg.id]
  }

  tags = {
    Project = var.project_name
  }
}

# Create the AWS Batch Job Queue
resource "aws_batch_job_queue" "auditor_queue" {
  name     = "${var.project_name}-queue"
  state    = "ENABLED"
  priority = 1

  # Use the new compute_environment_order format
  compute_environment_order {
    compute_environment = aws_batch_compute_environment.fargate_env.arn
    order               = 1
  }

  tags = {
    Project = var.project_name
  }
}

# Create the AWS Batch Job Definition
resource "aws_batch_job_definition" "ec2_auditor_job" {
  name                  = "${var.project_name}-job-definition"
  type                  = "container"
  platform_capabilities = ["FARGATE"]
  propagate_tags        = false

  # Parameters for the container
  container_properties = jsonencode({
    image = "${aws_ecr_repository.batch_job_repo.repository_url}:latest"
    jobRoleArn = data.aws_iam_role.oidc_role.arn
    executionRoleArn = data.aws_iam_role.oidc_role.arn
    resourceRequirements = [
      {
        type  = "VCPU"
        value = tostring(var.batch_job_vcpus)
      },
      {
        type  = "MEMORY"
        value = tostring(var.batch_job_memory)
      }
    ]
    environment = [
      {
        name  = "S3_BUCKET_NAME"
        value = aws_s3_bucket.audit_reports.id
      },
      {
        name  = "AWS_REGION"
        value = var.region
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/aws/batch/job"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = var.project_name
      }
    }
  })

  tags = {
    Project = var.project_name
  }
}

# Create CloudWatch Log Group for Batch jobs
resource "aws_cloudwatch_log_group" "batch_jobs" {
  name              = "/aws/batch/job"
  retention_in_days = 30

  tags = {
    Project = var.project_name
  }
}