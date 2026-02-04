#!/usr/bin/env python3
import boto3
import shutil
import requests
from datetime import datetime, timezone

# Get instance metadata
def get_instance_metadata():
    token = requests.put('http://169.254.169.254/latest/api/token',
                        headers={'X-aws-ec2-metadata-token-ttl-seconds': '21600'}).text
    instance_id = requests.get('http://169.254.169.254/latest/meta-data/instance-id',
                              headers={'X-aws-ec2-metadata-token': token}).text
    return instance_id

instance_id = get_instance_metadata()
cw = boto3.client('cloudwatch', region_name='us-east-1')

# Collect metrics
total, used, free = shutil.disk_usage('/')
disk_used_percent = (used / total) * 100

# Publish to CloudWatch
timestamp = datetime.now(timezone.utc)
print(f"{timestamp}: Publishing metrics for {instance_id}")
print(f"  disk_used_percent = {disk_used_percent:.2f}%")

cw.put_metric_data(
    Namespace='CWAgent',
    MetricData=[{
        'MetricName': 'disk_used_percent',
        'Value': disk_used_percent,
        'Unit': 'Percent',
        'Timestamp': timestamp,
        'Dimensions': [
            {'Name': 'InstanceId', 'Value': instance_id},
            {'Name': 'path', 'Value': '/'}
        ]
    }]
)

print("✓ Metrics published successfully to CloudWatch")
