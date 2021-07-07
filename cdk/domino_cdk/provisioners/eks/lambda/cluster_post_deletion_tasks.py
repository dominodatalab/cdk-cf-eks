import os

import boto3


def on_event(event, context):
    request_type = event['RequestType']
    if request_type == 'Create':
        return on_create(event)
    if request_type == 'Update':
        return None
    if request_type == 'Delete':
        return on_delete(event)
    raise Exception('Invalid request type: %s' % request_type)


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
