import os
import traceback

import boto3
import cfnresponse

client = boto3.client('backup')


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)

    request_type = event['RequestType']
    physical_resource_id = f"domino-cluster-{event['ResourceProperties']['stack_name']}-backup-cleanup"
    status = cfnresponse.FAILED

    try:
        if request_type == 'Delete':
            on_delete(event)
        status = cfnresponse.SUCCESS
    except:  # noqa: E722
        traceback.print_exc()

    cfnresponse.send(event, context, status, {}, physical_resource_id)


def on_delete(event):
    backup_vault_name = event['ResourceProperties']['backup_vault']
    print(f'Delete backup points in backup vault {backup_vault_name}')
    response = client.list_recovery_points_by_backup_vault(BackupVaultName=backup_vault_name)
    for rp in response['RecoveryPoints']:
        response = client.delete_recovery_point(
            BackupVaultName=backup_vault_name, RecoveryPointArn=rp['RecoveryPointArn']
        )
