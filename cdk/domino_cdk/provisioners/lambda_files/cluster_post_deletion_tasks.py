import json
import os

import boto3
import requests


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)
    request_type = event['RequestType']
    response = {}
    if request_type == 'Create':
        response = on_create(event)
    if request_type == 'Delete':
        response = on_delete(event)
    event.update(response)
    event['Status'] = 'SUCCESS'
    requests.put(event['ResponseURL'], data=json.dumps(event))


def on_create(event):
    cluster_name = os.environ['cluster']
    physical_id = f'domino-cluster-{cluster_name}-logs-cleanup'
    return {'PhysicalResourceId': physical_id}


def on_delete(event):
    logs_client = boto3.client('logs')
    cluster_name = os.environ['cluster']
    log_group_name = f'/aws/lambda/{cluster_name}'
    print(f'Change retention of all {log_group_name} log groups')
    response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name, limit=50)
    for lg in response['logGroups']:
        print(f'Change retention of log group {lg["logGroupName"]}')
        logs_client.put_retention_policy(logGroupName=lg['logGroupName'], retentionInDays=1)
    return {}