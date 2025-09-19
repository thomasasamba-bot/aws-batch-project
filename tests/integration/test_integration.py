"""Integration tests for AWS Resource Auditor main functionality."""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

def test_get_aws_clients():
    """Test that AWS clients can be created."""
    from src.main import get_aws_clients
    
    with patch('src.main.boto3.client') as mock_client:
        mock_ec2 = MagicMock()
        mock_s3 = MagicMock()
        mock_logs = MagicMock()
        
        mock_client.side_effect = [mock_ec2, mock_s3, mock_logs]
        
        ec2, s3, logs = get_aws_clients()
        
        assert ec2 == mock_ec2
        assert s3 == mock_s3
        assert logs == mock_logs

def test_check_instance_utilization():
    """Test instance utilization checking."""
    from src.main import check_instance_utilization
    
    # Test stopped instance
    stopped_instance = {
        'InstanceId': 'i-1234567890abcdef0',
        'State': {'Name': 'stopped'},
        'BlockDeviceMappings': [{'DeviceName': '/dev/sda1'}],
        'InstanceType': 't2.micro'
    }
    
    issues = check_instance_utilization(stopped_instance)
    assert len(issues) == 1
    assert issues[0]['issue'] == 'STOPPED_INSTANCE'

@patch('src.main.boto3.client')
def test_get_ec2_instances(mock_client):
    """Test retrieving EC2 instances."""
    from src.main import get_ec2_instances
    
    # Mock EC2 client and response
    mock_ec2 = MagicMock()
    mock_client.return_value = mock_ec2
    
    mock_response = {
        'Reservations': [
            {
                'Instances': [
                    {
                        'InstanceId': 'i-1234567890abcdef0',
                        'InstanceType': 't2.micro',
                        'State': {'Name': 'running'},
                        'ImageId': 'ami-12345678'
                    }
                ]
            }
        ]
    }
    mock_ec2.describe_instances.return_value = mock_response
    
    instances = get_ec2_instances(mock_ec2)
    assert len(instances) == 1
    assert instances[0]['InstanceType'] == 't2.micro'

def test_upload_to_s3():
    """Test uploading reports to S3."""
    from src.main import upload_to_s3
    
    # Mock S3 client
    mock_s3 = MagicMock()
    mock_s3.put_object.return_value = {}
    
    test_content = json.dumps({'test': 'data'})
    key = upload_to_s3(mock_s3, test_content, 'test.json', 'application/json', 'test-bucket')
    
    assert key is not None
    assert key.startswith('audit-reports/')
    mock_s3.put_object.assert_called_once()

def test_analyze_own_logs():
    """Test analyzing CloudWatch logs."""
    from src.main import analyze_own_logs
    
    # Mock logs client
    mock_logs = MagicMock()
    mock_logs.describe_log_streams.return_value = {
        'logStreams': [{'logStreamName': 'test-stream'}]
    }
    mock_logs.get_log_events.return_value = {
        'events': [
            {'message': 'INFO: Test message'},
            {'message': 'ERROR: Test error'}
        ]
    }
    
    with patch('src.main.os.getenv') as mock_getenv:
        mock_getenv.return_value = '/aws/batch/job'
        analysis = analyze_own_logs(mock_logs, 'test-job-123')
        
        assert analysis['total_log_events'] == 2
        assert analysis['error_count'] == 1

@patch('src.main.boto3.client')
def test_generate_audit_report(mock_client):
    """Test audit report generation."""
    from src.main import generate_audit_report
    
    # Mock EC2 client
    mock_ec2 = MagicMock()
    mock_client.return_value = mock_ec2
    
    # Mock instances data
    mock_instances = [
        {
            'InstanceId': 'i-1234567890abcdef0',
            'State': {'Name': 'running'},
            'SecurityGroups': [{'GroupId': 'sg-12345678'}],
            'InstanceType': 't2.micro'
        }
    ]
    
    # Mock security group response
    mock_ec2.describe_security_group_rules.return_value = {
        'SecurityGroupRules': []
    }
    
    report = generate_audit_report(mock_ec2, mock_instances)
    
    assert report['summary']['total_instances'] == 1
    assert 'audit_timestamp' in report
    assert 'findings' in report