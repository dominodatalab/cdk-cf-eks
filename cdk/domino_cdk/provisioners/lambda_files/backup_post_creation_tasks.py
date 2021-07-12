import json
import os
import traceback

import boto3
import requests

client = boto3.client('backup')


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
    physical_id = f"domino-cluster-{event['ResourceProperties']['stack_name']}-backup-cleanup"
    return {'PhysicalResourceId': physical_id}


def on_delete(event):
    backup_vault_name = event['ResourceProperties']['backup_vault']
    print(f'Delete backup points in backup vault {backup_vault_name}')
    response = client.list_recovery_points_by_backup_vault(BackupVaultName=backup_vault_name)
    for rp in response['RecoveryPoints']:
        response = client.delete_recovery_point(
            BackupVaultName=backup_vault_name, RecoveryPointArn=rp['RecoveryPointArn']
        )
    return {}
