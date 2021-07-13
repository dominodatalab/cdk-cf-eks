import json
import os
import traceback

import boto3
import requests


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)
    request_type = event['RequestType']
    response = {}
    try:
        if request_type == 'Create':
            response = on_create(event)
        if request_type == 'Delete':
            response = on_delete(event)
        if response:
            event.update(response)
        event['Status'] = 'SUCCESS'
    except:  # noqa: E722
        traceback.print_exc()
        event['Status'] = 'FAILED'
    requests.put(event['ResponseURL'], data=json.dumps(event))


def on_create(event):
    cluster_name = event['ResourceProperties']['cluster_name']
    physical_id = f'domino-cluster-{cluster_name}-logs-cleanup'
    return {'PhysicalResourceId': physical_id}


def on_delete(event):
    logs_client = boto3.client('logs')
    cluster_name = event['ResourceProperties']['cluster_name']
    set_log_groups_retention(f'/aws/lambda/{cluster_name}', logs_client)
    set_log_groups_retention(f'/aws/eks/{cluster_name}/cluster', logs_client)
    return {}


def set_log_groups_retention(log_group_name_prefix, logs_client):
    print(f'Change retention of all {log_group_name_prefix}* log groups')
    response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name_prefix, limit=50)
    for lg in response['logGroups']:
        print(f'Change retention of log group {lg["logGroupName"]}')
        logs_client.put_retention_policy(logGroupName=lg['logGroupName'], retentionInDays=1)
