import os
import time
import traceback

import boto3
import cfnresponse


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)

    request_type = event['RequestType']
    cluster_name = event['ResourceProperties']['cluster_name']
    physical_resource_id = f'domino-cluster-{cluster_name}-eks-cluster-task'
    status = cfnresponse.FAILED

    try:
        if request_type == 'Create':
            on_create(event)
        if request_type == 'Update':
            on_update(event)
        status = cfnresponse.SUCCESS
    except:  # noqa: E722
        traceback.print_exc()

    cfnresponse.send(event, context, status, {}, physical_resource_id)


def tag_cluster(event, eks_client):
    cluster_arn = event['ResourceProperties']['cluster_arn']
    print(f'Tag cluster {cluster_arn}')
    eks_client.tag_resource(
        resourceArn=cluster_arn,
        tags=event['ResourceProperties']['tags'],
    )


def on_update(event):
    eks_client = boto3.client('eks')
    tag_cluster(event, eks_client)


def on_create(event):
    logs_client = boto3.client('logs')
    eks_client = boto3.client('eks')
    cluster_name = event['ResourceProperties']['cluster_name']

    tag_cluster(event, eks_client)

    print(f'Enable logging in cluster {cluster_name}')
    try:
        eks_client.update_cluster_config(
            name=cluster_name,
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

    while not set_log_groups_retention(f'/aws/eks/{cluster_name}/cluster', logs_client):
        # No limit here. Wait till lambda timeout is reached
        time.sleep(30)


def set_log_groups_retention(log_group_name_prefix, logs_client):
    print(f'Change retention of all {log_group_name_prefix}* log groups')
    response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name_prefix, limit=50)
    for lg in response['logGroups']:
        print(f'Change retention of log group {lg["logGroupName"]}')
        logs_client.put_retention_policy(logGroupName=lg['logGroupName'], retentionInDays=7)
    return len(response['logGroups'])
