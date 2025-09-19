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

# Create an IAM role that the Batch job will assume
resource "aws_iam_role" "batch_job_execution_role" {
  name = "${var.project_name}-execution-role"

  # Trust policy: who can assume this role? (AWS Batch service)
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "batch.amazonaws.com"
        }
      },
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = var.project_name
  }
}

# Attach policies to the IAM role to grant necessary permissions
# This is a CUSTOM policy for our specific job's needs
resource "aws_iam_policy" "batch_job_policy" {
  name        = "${var.project_name}-job-policy"
  description = "Permissions for the EC2 auditor batch job to access S3, EC2, and CloudWatch Logs."

  # Policy Document: what permissions does the role have?
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeSecurityGroupRules" # Needed for our enhanced security check
        ]
        Resource = "*" # Required for describe actions
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.audit_reports.arn}/audit-reports/*" # Least privilege: only the reports folder
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogStreams",
          "logs:GetLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/batch/job:*" # Permission to read its own logs
      }
    ]
  })
}

# Attach the custom policy to the role
resource "aws_iam_role_policy_attachment" "batch_job_policy_attachment" {
  role       = aws_iam_role.batch_job_execution_role.name
  policy_arn = aws_iam_policy.batch_job_policy.arn
}

# Attach the standard AWS managed policy for ECR access (to pull the image)
resource "aws_iam_role_policy_attachment" "batch_ecr_power_user_attachment" {
  role       = aws_iam_role.batch_job_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

# Create the AWS Batch Compute Environment (Fargate)
resource "aws_batch_compute_environment" "fargate_env" {
  compute_environment_name = "${var.project_name}-fargate-env"
  type                     = "MANAGED"
  state                    = "ENABLED"
  service_role             = aws_iam_role.batch_job_execution_role.arn

  compute_resources {
    type       = "FARGATE"
    max_vcpus  = 4
    
    # Use the subnets and security group we created
    subnets            = data.aws_subnets.available.ids
    security_group_ids = [aws_security_group.batch_sg.id]
  }

  depends_on = [aws_iam_role_policy_attachment.batch_ecr_power_user_attachment]

  tags = {
    Project = var.project_name
  }
}

# Create the AWS Batch Job Queue
resource "aws_batch_job_queue" "auditor_queue" {
  name     = "${var.project_name}-queue"
  state    = "ENABLED"
  priority = 1

  # Use the new compute_environment_order format (old format is deprecated)
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
    jobRoleArn = aws_iam_role.batch_job_execution_role.arn
    executionRoleArn = aws_iam_role.batch_job_execution_role.arn
    resourceRequirements = [
      {
        type  = "VCPU"
        value = tostring(var.batch_job_vcpus)  # Convert to string
      },
      {
        type  = "MEMORY"
        value = tostring(var.batch_job_memory) # Convert to string
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
  retention_in_days = 30  # Keep logs for 30 days

  tags = {
    Project = var.project_name
  }
}

# Create CloudWatch Dashboard for monitoring
resource "aws_cloudwatch_dashboard" "batch_auditor_dashboard" {
  dashboard_name = "${var.project_name}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Batch", "SubmittedJobs", "JobQueue", "${aws_batch_job_queue.auditor_queue.name}"],
            [".", "SucceededJobs", ".", "."],
            [".", "FailedJobs", ".", "."]
          ]
          period = 300
          stat   = "Sum"
          region = var.region
          title  = "Batch Job Metrics"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/EC2", "CPUUtilization", "AutoScalingGroupName", "${var.project_name}-fargate-env"],
            [".", "MemoryUtilization", ".", "."]
          ]
          period = 300
          stat   = "Average"
          region = var.region
          title  = "Fargate Resource Utilization"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 6
        width  = 24
        height = 6
        properties = {
          region = var.region
          title  = "Recent Batch Job Logs"
          query  = <<EOF
SOURCE '${aws_cloudwatch_log_group.batch_jobs.name}' | 
fields @timestamp, @message |
sort @timestamp desc |
limit 20
EOF
          view   = "table"
        }
      }
    ]
  })
}

# CloudWatch Alarm for failed jobs
resource "aws_cloudwatch_metric_alarm" "batch_job_failures" {
  alarm_name          = "${var.project_name}-job-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FailedJobs"
  namespace           = "AWS/Batch"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "This alarm triggers when AWS Batch jobs fail"
  treat_missing_data  = "notBreaching"

  dimensions = {
    JobQueue = aws_batch_job_queue.auditor_queue.name
  }

  alarm_actions = []  # Add SNS topic ARN here for notifications

  tags = {
    Project = var.project_name
  }
}