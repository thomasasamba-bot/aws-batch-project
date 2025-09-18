"""Configuration for integration tests."""
import pytest
import boto3
from moto import mock_ec2, mock_s3, mock_logs

@pytest.fixture(autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    import os
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

@pytest.fixture
def ec2_client():
    """Mock EC2 client."""
    with mock_ec2():
        yield boto3.client('ec2', region_name='us-east-1')

@pytest.fixture
def s3_client():
    """Mock S3 client."""
    with mock_s3():
        yield boto3.client('s3', region_name='us-east-1')

@pytest.fixture
def logs_client():
    """Mock CloudWatch Logs client."""
    with mock_logs():
        yield boto3.client('logs', region_name='us-east-1')