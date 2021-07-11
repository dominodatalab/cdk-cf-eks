import json
import os

import boto3
import requests

client = boto3.client('backup')


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)
    request_type = event['RequestType']
    response = {}
    if request_type == 'Create':
        response = on_create(event)
    if request_type == 'Delete':
        response = on_delete(event)
    if response:
        event.update(response)
    event['Status'] = 'SUCCESS'
    requests.put(event['ResponseURL'], data=json.dumps(event))


def on_create(event):
    os.system(
        f'''
        export PATH=$PATH:/opt/awscli:/opt/kubectl
        export KUBECONFIG=/tmp/kubeconfig
        aws eks update-kubeconfig --name {os.environ["cluster_name"]} --kubeconfig $KUBECONFIG
        chmod 400 $KUBECONFIG
        mkdir /tmp/install
        cp * /tmp/install
        cd /tmp/install
        tar xvf tigera-operator-v3.18.4-1.tgz
        for t in 1 2 3 4 5 6 7 8
        do
            # somehow the credentials are not ready immediately
            /opt/helm/helm install calico ./tigera-operator -f values.yaml && exit 0
            sleep 5
        done
        '''
    )
    physical_id = f'{os.environ["AWS_LAMBDA_FUNCTION_NAME"]}-custom'
    return {'PhysicalResourceId': physical_id}


def on_delete(event):
    return {}
