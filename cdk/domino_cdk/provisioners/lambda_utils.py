from os import path
from typing import Dict, List

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_logs as logs
from aws_cdk import core as cdk
from aws_cdk.lambda_layer_awscli import AwsCliLayer
from aws_cdk.lambda_layer_kubectl import KubectlLayer


def create_lambda(
    scope: cdk.Construct,
    stack_name: str,
    name: str,
    environment: Dict[str, str],
    resources: List[str],
    actions: List[str],
) -> cdk.Construct:
    dirname = path.dirname(path.abspath(__file__))
    with open(path.join(dirname, "lambda_files", f"{name}.py"), encoding="utf-8") as fp:
        on_event_code_body = fp.read()
    on_event = lambda_.Function(
        scope,
        f"{name}_on_event",
        function_name=f"{stack_name}-{name}",
        runtime=lambda_.Runtime.PYTHON_3_7,
        handler="index.on_event",
        code=lambda_.InlineCode(on_event_code_body),
        environment=environment,
        timeout=cdk.Duration.seconds(180),  # default is 3 seconds
        log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
    )
    statement = iam.PolicyStatement()
    for r in resources:
        statement.add_resources(r)
    for a in actions:
        statement.add_actions(a)
    on_event.add_to_role_policy(statement)

    return cdk.CustomResource(scope, f"{name}_custom", service_token=on_event.function_arn)


def helm_lambda(scope: cdk.Construct, name: str, cluster: eks.Cluster, vpc: ec2.Vpc) -> cdk.Construct:
    dirname = path.dirname(path.abspath(__file__))
    on_event = lambda_.Function(
        scope,
        f"{name}_on_event",
        function_name=f"{cluster.cluster_name}-{name}",
        runtime=lambda_.Runtime.PYTHON_3_7,
        layers=[
            KubectlLayer(scope, "KubectlLayer"),
            AwsCliLayer(scope, "AwsCliLayer"),
        ],
        handler="main.on_event",
        code=lambda_.Code.from_asset(path.join(dirname, f"{name}_lambda_code")),
        environment={
            "cluster_name": cluster.cluster_name,
        },
        timeout=cdk.Duration.seconds(180),  # default is 3 seconds
        log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
        security_groups=cluster.connections.security_groups,
        vpc=vpc,
    )
    cluster.connections.allow_default_port_from(cluster.connections)
    statement = iam.PolicyStatement()
    statement.add_resources(cluster.cluster_arn)
    statement.add_actions("eks:DescribeCluster")
    on_event.add_to_role_policy(statement)
    cluster.aws_auth.add_masters_role(on_event.role)

    return cdk.CustomResource(scope, f"{name}_custom", service_token=on_event.function_arn)
