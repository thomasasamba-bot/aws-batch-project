"""Integration tests for the AWS Resource Auditor."""
import json
import pytest
from unittest.mock import patch

from src.main import get_ec2_instances, upload_to_s3, analyze_own_logs

def test_get_ec2_instances(ec2_client):
    """Test getting EC2 instances with mocked AWS."""
    # Create a test instance
    ec2_client.run_instances(ImageId='ami-12345678', MinCount=1, MaxCount=1)
    
    instances = get_ec2_instances(ec2_client)
    assert len(instances) == 1
    assert instances[0]['ImageId'] == 'ami-12345678'

def test_upload_to_s3(s3_client):
    """Test uploading to S3 with mocked AWS."""
    # Create a test bucket
    bucket_name = 'test-bucket'
    s3_client.create_bucket(Bucket=bucket_name)
    
    content = json.dumps({'test': 'data'})
    key = upload_to_s3(s3_client, content, 'test.json', 'application/json', bucket_name)
    
    assert key is not None
    # Verify the object exists
    response = s3_client.list_objects_v2(Bucket=bucket_name)
    assert 'Contents' in response
    assert len(response['Contents']) == 1

def test_analyze_own_logs(logs_client):
    """Test analyzing CloudWatch logs with mocked AWS."""
    # Create a log group and stream
    log_group_name = '/aws/batch/job'
    log_stream_name = 'test-job-id'
    
    logs_client.create_log_group(logGroupName=log_group_name)
    logs_client.create_log_stream(
        logGroupName=log_group_name,
        logStreamName=log_stream_name
    )
    
    # Put some test log events
    logs_client.put_log_events(
        logGroupName=log_group_name,
        logStreamName=log_stream_name,
        logEvents=[
            {'timestamp': 1234567890000, 'message': 'INFO: Test log message'},
            {'timestamp': 1234567891000, 'message': 'ERROR: Test error message'}
        ]
    )
    
    with patch('src.main.os.getenv') as mock_getenv:
        mock_getenv.return_value = log_group_name
        analysis = analyze_own_logs(logs_client, 'test-job-id')
        
        assert analysis['total_log_events'] == 2
        assert analysis['error_count'] == 1