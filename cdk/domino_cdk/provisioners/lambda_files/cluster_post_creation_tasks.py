import json
import os
import time

import boto3
import requests


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)
    request_type = event['RequestType']
    response = {}
    if request_type == 'Create':
        response = on_create(event)
    event.update(response)
    event['Status'] = 'SUCCESS'
    requests.put(event['ResponseURL'], data=json.dumps(event))


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
    try:
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
    except eks_client.exceptions.InvalidParameterException as e:
        if "No changes needed for the logging config provided" not in e.response["Error"]["Message"]:
            raise

    log_group_name = f'/aws/eks/{cluster_name}/cluster'
    print(f'Change retention of {log_group_name} log group')
    while True:  # wait till lambda timeout is reached
        response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name, limit=50)
        if response['logGroups']:
            break
        time.sleep(30)
    logs_client.put_retention_policy(logGroupName=log_group_name, retentionInDays=7)

    physical_id = f'domino-cluster-{cluster_name}-eks-cluster-task'
    return {'PhysicalResourceId': physical_id}
