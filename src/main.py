#!/usr/bin/env python3
"""
AWS Resource Auditor & Self-Analyzing Batch Job

1. Audits EC2 instances for security misconfigurations and cost savings.
2. Fetches its own CloudWatch Logs to analyze execution.
3. Produces a final report combining audit findings and operational metrics.

Designed to run on AWS Batch with Fargate.
"""

import json
import logging
import os
import time
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# Configure logging to stdout (critical for CloudWatch)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_aws_clients():
    """Initializes and returns AWS clients for the audit and for CloudWatch Logs."""
    region = os.getenv('AWS_REGION', 'us-east-1')
    logger.info(f"Initializing AWS clients in region: {region}")

    return (
        boto3.client('ec2', region_name=region),
        boto3.client('s3', region_name=region),
        boto3.client('logs', region_name=region)  # For self-analysis
    )

def get_ec2_instances(ec2_client):
    """Retrieve all EC2 instances in the region."""
    try:
        logger.info("Fetching EC2 instances...")
        response = ec2_client.describe_instances()
        instances = []

        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instances.append(instance)

        logger.info(f"Found {len(instances)} EC2 instances.")
        return instances
    except ClientError as e:
        logger.error(f"Error fetching EC2 instances: {e}")
        return []

def check_security_groups(ec2_client, instance):
    """Check if instance has security groups allowing SSH/RDP from anywhere."""
    security_issues = []

    for sg in instance.get('SecurityGroups', []):
        sg_id = sg['GroupId']

        try:
            sg_response = ec2_client.describe_security_group_rules(
                Filters=[{'Name': 'group-id', 'Values': [sg_id]}]
            )

            for rule in sg_response['SecurityGroupRules']:
                if (rule.get('FromPort') in [22, 3389] and
                    rule.get('IpProtocol') == 'tcp'):
                    if '0.0.0.0/0' in rule.get('CidrIpv4', ''):
                        security_issues.append({
                            'SecurityGroupId': sg_id,
                            'Port': rule['FromPort'],
                            'Protocol': rule['IpProtocol'],
                            'CIDR': rule.get('CidrIpv4')
                        })
        except ClientError as e:
            logger.error(f"Error checking security group {sg_id}: {e}")

    return security_issues

def check_instance_utilization(instance):
    """Check if instance might be underutilized (simplified check)."""
    utilization_issues = []

    instance_id = instance['InstanceId']
    state = instance['State']['Name']

    # Check for stopped instances with EBS volumes
    if state == 'stopped' and instance.get('BlockDeviceMappings'):
        utilization_issues.append({
            'issue': 'STOPPED_INSTANCE',
            'message': 'Instance is stopped but still incurring EBS storage costs',
            'instance_id': instance_id
        })

    # Simple, free-tier friendly check: flag if instance is not using free tier eligible types
    free_tier_types = ['t2.micro', 't3.micro', 't4g.micro']
    instance_type = instance['InstanceType']
    if instance_type not in free_tier_types and state == 'running':
        utilization_issues.append({
            'issue': 'NON_FREE_TIER_TYPE',
            'message': f'Instance type {instance_type} may incur costs. Free tier types: {", ".join(free_tier_types)}',
            'instance_id': instance_id,
            'current_type': instance_type,
        })

    return utilization_issues

def generate_audit_report(ec2_client, instances):
    """Generate the core EC2 audit report."""
    logger.info("Generating EC2 audit report...")
    report = {
        'audit_timestamp': datetime.utcnow().isoformat(),
        'findings': {
            'security_issues': [],
            'utilization_issues': []
        },
        'summary': {
            'total_instances': len(instances),
            'instances_with_security_issues': 0,
            'instances_with_utilization_issues': 0
        }
    }

    for instance in instances:
        instance_id = instance['InstanceId']

        # Check security groups
        security_issues = check_security_groups(ec2_client, instance)
        if security_issues:
            report['findings']['security_issues'].append({
                'instance_id': instance_id,
                'issues': security_issues
            })
            report['summary']['instances_with_security_issues'] += 1

        # Check utilization
        utilization_issues = check_instance_utilization(instance)
        if utilization_issues:
            report['findings']['utilization_issues'].append({
                'instance_id': instance_id,
                'issues': utilization_issues
            })
            report['summary']['instances_with_utilization_issues'] += 1

    return report

def upload_to_s3(s3_client, content, key_suffix, content_type, bucket_name):
    """Upload a report to S3."""
    try:
        key = f"audit-reports/ec2-audit-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{key_suffix}"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=content,
            ContentType=content_type
        )
        logger.info(f"Uploaded to S3: {key}")
        return key
    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        return None

def analyze_own_logs(logs_client, job_id):
    """Fetches and analyzes the CloudWatch Logs for this job (self-analysis)."""
    log_group_name = os.getenv('AWS_BATCH_LOG_GROUP_NAME', '/aws/batch/job')
    log_stream_prefix = job_id

    try:
        # Find the log stream for this job
        response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            logStreamNamePrefix=log_stream_prefix,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )

        if not response['logStreams']:
            return {"error": "No log stream found for self-analysis."}

        log_stream_name = response['logStreams'][0]['logStreamName']
        logger.info(f"Found own log stream: {log_stream_name}")

        # Get the log events
        log_response = logs_client.get_log_events(
            logGroupName=log_group_name,
            logStreamName=log_stream_name,
            startFromHead=False
        )

        events = log_response['events']
        log_messages = [event['message'] for event in events]

        # Perform analysis
        analysis = {
            'log_analysis_timestamp': datetime.utcnow().isoformat(),
            'total_log_events': len(events),
            'error_count': sum(1 for msg in log_messages if 'ERROR' in msg),
            'warning_count': sum(1 for msg in log_messages if 'WARNING' in msg),
            'first_log_event': events[-1]['message'] if events else None,
            'last_log_event': events[0]['message'] if events else None,
            'successful_completion': any("FINAL JOB SUMMARY" in msg for msg in log_messages)
        }

        return analysis

    except ClientError as e:
        logger.error(f"Error during self-analysis of logs: {e}")
        return {"error": str(e)}

def main():
    """Main function to run the combined audit and self-analysis."""
    start_time = time.time()
    job_id = os.getenv('AWS_BATCH_JOB_ID', 'local-test-job-id')
    s3_bucket_name = os.getenv('S3_BUCKET_NAME', 'aws-batch-audit-reports')

    logger.info("🚀 Starting Combined AWS Batch Job: EC2 Audit + Self-Analysis")
    logger.info(f"Job ID: {job_id}")
    logger.info(f"Target S3 Bucket: {s3_bucket_name}")

    # Get AWS clients
    ec2_client, s3_client, logs_client = get_aws_clients()

    # --- PHASE 1: Perform EC2 Audit ---
    instances = get_ec2_instances(ec2_client)
    audit_report = generate_audit_report(ec2_client, instances)

    # Upload JSON audit report
    audit_json = json.dumps(audit_report, indent=2)
    upload_to_s3(s3_client, audit_json, 'report.json', 'application/json', s3_bucket_name)

    # Generate and upload Markdown summary
    markdown_content = [
        "# AWS EC2 Instance Audit Report",
        f"**Generated:** {audit_report['audit_timestamp']}",
        f"**Job ID:** {job_id}",
        "",
        "## Summary",
        f"- Total Instances: {audit_report['summary']['total_instances']}",
        f"- Instances with Security Issues: {audit_report['summary']['instances_with_security_issues']}",
        f"- Instances with Utilization Issues: {audit_report['summary']['instances_with_utilization_issues']}",
    ]
    markdown_report = "\n".join(markdown_content)
    upload_to_s3(s3_client, markdown_report, 'summary.md', 'text/markdown', s3_bucket_name)

    # --- PHASE 2: Self-Analysis via CloudWatch Logs ---
    logger.info("🔍 Beginning self-analysis via CloudWatch Logs...")
    time.sleep(5)  # Brief pause for log ingestion
    log_analysis = analyze_own_logs(logs_client, job_id)

    # --- PHASE 3: Generate Final Combined Report ---
    end_time = time.time()
    execution_duration = end_time - start_time

    final_report = {
        'job_id': job_id,
        'execution_duration_seconds': round(execution_duration, 2),
        'audit_summary': audit_report['summary'],
        'operational_metrics': {
            'start_time': datetime.fromtimestamp(start_time, timezone.utc).isoformat(),
            'end_time': datetime.fromtimestamp(end_time, timezone.utc).isoformat(),
            'log_analysis': log_analysis
        },
        'status': 'SUCCESS' if log_analysis.get('successful_completion') else 'ANALYSIS_COMPLETED_WITH_WARNINGS'
    }

    # Upload the final combined report
    final_report_json = json.dumps(final_report, indent=2)
    upload_to_s3(s3_client, final_report_json, 'final-combined-report.json', 'application/json', s3_bucket_name)

    # Log the final summary
    logger.info(f"📈 FINAL JOB SUMMARY: {json.dumps(final_report, indent=2)}")
    logger.info("🏁 Combined audit and self-analysis job finished successfully.")

    # Exit successfully
    sys.exit(0)

if __name__ == "__main__":
    main()