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
        if request_type == 'Update':
            response = on_update(event)
        if response:
            event.update(response)
        event['Status'] = 'SUCCESS'
    except:  # noqa: E722
        traceback.print_exc()
        event['Status'] = 'FAILED'
    requests.put(event['ResponseURL'], data=json.dumps(event))


def tag_ec2(tags, stack_name, vpc_id):
    print("Tagging stuff!")
    resource_ids = []

    client = boto3.client("ec2")
    vpc_filter = [{"Name": "vpc-id", "Values": [vpc_id]}]

    endpoints = client.describe_vpc_endpoints(Filters=vpc_filter)
    resource_ids.extend([ep["VpcEndpointId"] for ep in endpoints["VpcEndpoints"]])

    route_tables = client.describe_route_tables(Filters=vpc_filter)
    resource_ids.extend([rt["RouteTableId"] for rt in route_tables["RouteTables"]])
    # If we want to restrict to the default one, we could do:
    # [rt for rt in rts if not rt["Tags"]] or search for main one

    security_groups = client.describe_security_groups(Filters=[*vpc_filter, {"Name": "group-name", "Values": ["default"]}])
    resource_ids.append(security_groups["SecurityGroups"][0]["GroupId"])

    network_acls = client.describe_network_acls(Filters=vpc_filter)
    resource_ids.extend([acl["NetworkAclId"] for acl in network_acls["NetworkAcls"]])

    # "Our" Launch Templates either have our deploy name in their name, or have a basic eks cluster tag with the deploy name
    # Potentially just have CDK pass these?
    launch_templates = client.describe_launch_templates()
    our_lts = [lt for lt in launch_templates["LaunchTemplates"] if stack_name in lt['LaunchTemplateName'] or stack_name in [v["Value"] for v in lt.get("Tags", [])]]
    resource_ids.extend([lt["LaunchTemplateId"] for lt in our_lts])

    print(resource_ids)

    client.create_tags(Resources=resource_ids, Tags=tags)


def tag_iam(tags, stack_name):
    client = boto3.client("iam")

    # Similarly to launch templates, could we just have cdk give us these?
    policy_arns = [p["Arn"] for p in client.list_policies()["Policies"] if stack_name in p["PolicyName"]]
    for arn in policy_arns:
        client.tag_policy(PolicyArn=arn, Tags=tags)


def tag_stuff(event):
    tags = [{"Key": k, "Value": v} for k, v in event['ResourceProperties']['tags'].items()]
    stack_name = event["ResourceProperties"]["stack_name"]
    vpc_id = event['ResourceProperties']['vpc_id']

    tag_ec2(tags, stack_name, vpc_id)
    tag_iam(tags, stack_name)


def on_update(event):
    tag_stuff(event)


def on_create(event):
    tag_stuff(event)

    physical_id = f'domino-tag-fixer-{event["ResourceProperties"]["stack_name"]}'
    return {'PhysicalResourceId': physical_id}
