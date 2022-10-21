import os
import traceback

import boto3
import cfnresponse


def on_event(event, context):
    print('Debug: event: ', event)
    print('Debug: environ:', os.environ)

    request_type = event['RequestType']
    physical_resource_id = f'domino-tag-fixer-{event["ResourceProperties"]["stack_name"]}'
    status = cfnresponse.FAILED

    try:
        if request_type == 'Create':
            tag_stuff(event)
        if request_type == 'Update':
            tag_stuff(event)

        status = cfnresponse.SUCCESS
    except:  # noqa: E722
        traceback.print_exc()

    cfnresponse.send(event, context, status, {}, physical_resource_id)


def tag_ec2(tags, stack_name, vpc_id, resource_ids):
    print("Tagging stuff!")

    client = boto3.client("ec2")
    vpc_filter = [{"Name": "vpc-id", "Values": [vpc_id]}]

    endpoints = client.describe_vpc_endpoints(Filters=vpc_filter)
    resource_ids.extend([ep["VpcEndpointId"] for ep in endpoints["VpcEndpoints"]])

    route_tables = client.describe_route_tables(Filters=vpc_filter)
    resource_ids.extend([rt["RouteTableId"] for rt in route_tables["RouteTables"]])
    # If we want to restrict to the default one, we could do:
    # [rt for rt in rts if not rt["Tags"]] or search for main one

    security_groups = client.describe_security_groups(
        Filters=[*vpc_filter, {"Name": "group-name", "Values": ["default"]}]
    )
    resource_ids.append(security_groups["SecurityGroups"][0]["GroupId"])

    network_acls = client.describe_network_acls(Filters=vpc_filter)
    resource_ids.extend([acl["NetworkAclId"] for acl in network_acls["NetworkAcls"]])

    print(resource_ids)

    client.create_tags(Resources=resource_ids, Tags=tags)


def tag_iam(tags, stack_name, resource_arns):
    client = boto3.client("iam")

    print(f"IAM resources to tag: {resource_arns}")

    for arn in resource_arns:
        client.tag_policy(PolicyArn=arn, Tags=tags)


def tag_stuff(event):
    tags = [{"Key": k, "Value": v} for k, v in event['ResourceProperties']['tags'].items()]
    stack_name = event["ResourceProperties"]["stack_name"]
    vpc_id = event['ResourceProperties']['vpc_id']
    untagged_resources = event["ResourceProperties"]["untagged_resources"]

    tag_ec2(tags, stack_name, vpc_id, untagged_resources["ec2"])
    tag_iam(tags, stack_name, untagged_resources["iam"])
