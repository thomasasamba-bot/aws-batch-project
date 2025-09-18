# terraform/outputs.tf
output "ecr_repository_url" {
  description = "The URL of the ECR repository where the Docker image must be pushed."
  value       = aws_ecr_repository.batch_job_repo.repository_url
}

output "s3_bucket_name" {
  description = "The name of the S3 bucket created for audit reports."
  value       = aws_s3_bucket.audit_reports.id
}

output "batch_job_definition_name" {
  description = "The name of the AWS Batch job definition."
  value       = aws_batch_job_definition.ec2_auditor_job.name
}

output "batch_job_queue_name" {
  description = "The name of the AWS Batch job queue."
  value       = aws_batch_job_queue.auditor_queue.name
}