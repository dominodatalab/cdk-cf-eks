import json
import os
import time

import boto3


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)
    request_type = event['RequestType']
    if request_type == 'Create':
        return on_create(event)
    if request_type == 'Update':
        return None
    if request_type == 'Delete':
        return None
    raise Exception('Invalid request type: %s' % request_type)


def on_create(event):
    logs_client = boto3.client('logs')
    eks_client = boto3.client('eks')
    cluster_name = os.environ["cluster"]
    cluster_arn = os.environ["cluster_arn"]

    print(f'Tag cluster {cluster_arn}')
    eks_client.tag_resource(
        resourceArn=cluster_arn,
        tags=json.loads(os.environ['tags']),
    )

    print(f'Enable logging in cluster {cluster_arn}')
    eks_client.update_cluster_config(
        name=os.environ['cluster'],
        logging={
            "clusterLogging": [
                {
                    "enabled": True,
                    "types": ["api", "audit", "authenticator", "controllerManager", "scheduler"],
                },
            ],
        },
    )

    log_group_name = f'/aws/eks/{cluster_name}/cluster'
    print(f'Change retention of {log_group_name} log group')
    while True:  # wait till lambda timeout is reached
        response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name, limit=50)
        if response['logGroups']:
            break
        time.sleep(30)
    logs_client.put_retention_policy(logGroupName=log_group_name, retentionInDays=7)

    physical_id = f'domino-cluster-{cluster_name}-log-retention'
    return {'PhysicalResourceId': physical_id}
