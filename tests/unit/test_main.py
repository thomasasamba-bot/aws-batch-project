#!/usr/bin/env python3
"""Unit tests for the AWS Resource Auditor."""

import json
import os
import sys
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from main import check_security_groups, check_instance_utilization, generate_audit_report

def test_check_security_groups():
    """Test security group checking logic."""
    mock_ec2 = Mock()
    mock_instance = {
        'InstanceId': 'i-1234567890abcdef0',
        'SecurityGroups': [{'GroupId': 'sg-12345678'}]
    }
    
    # Mock security group rules response
    mock_ec2.describe_security_group_rules.return_value = {
        'SecurityGroupRules': [
            {
                'FromPort': 22,
                'IpProtocol': 'tcp',
                'CidrIpv4': '0.0.0.0/0'
            },
            {
                'FromPort': 80,
                'IpProtocol': 'tcp',
                'CidrIpv4': '0.0.0.0/0'
            }
        ]
    }
    
    issues = check_security_groups(mock_ec2, mock_instance)
    assert len(issues) == 1
    assert issues[0]['Port'] == 22

def test_check_instance_utilization():
    """Test instance utilization checking logic."""
    # Test stopped instance with EBS volumes
    stopped_instance = {
        'InstanceId': 'i-1234567890abcdef0',
        'State': {'Name': 'stopped'},
        'BlockDeviceMappings': [{'DeviceName': '/dev/sda1'}],
        'InstanceType': 't2.micro'
    }
    
    issues = check_instance_utilization(stopped_instance)
    assert len(issues) == 1
    assert issues[0]['issue'] == 'STOPPED_INSTANCE'
    
    # Test non-free tier instance
    non_free_instance = {
        'InstanceId': 'i-1234567890abcdef1',
        'State': {'Name': 'running'},
        'InstanceType': 'm5.large'
    }
    
    issues = check_instance_utilization(non_free_instance)
    assert len(issues) == 1
    assert issues[0]['issue'] == 'NON_FREE_TIER_TYPE'

def test_generate_audit_report():
    """Test audit report generation."""
    mock_ec2 = Mock()
    instances = [
        {
            'InstanceId': 'i-1234567890abcdef0',
            'State': {'Name': 'running'},
            'SecurityGroups': [{'GroupId': 'sg-12345678'}],
            'InstanceType': 't2.micro'
        }
    ]
    
    # Mock security group check to return no issues
    with patch('main.check_security_groups', return_value=[]):
        with patch('main.check_instance_utilization', return_value=[]):
            report = generate_audit_report(mock_ec2, instances)
            
            assert report['summary']['total_instances'] == 1
            assert report['summary']['instances_with_security_issues'] == 0
            assert report['summary']['instances_with_utilization_issues'] == 0

if __name__ == '__main__':
    test_check_security_groups()
    test_check_instance_utilization()
    test_generate_audit_report()
    print("All unit tests passed!")