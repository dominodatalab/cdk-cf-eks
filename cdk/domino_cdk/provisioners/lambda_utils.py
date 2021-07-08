from os import path
from typing import Dict, List

import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_logs as logs
from aws_cdk import core as cdk


def create_lambda(
    scope: cdk.Construct,
    stack_name: str,
    name: str,
    environment: Dict[str, str],
    resources: List[str],
    actions: List[str],
) -> cdk.Construct:
    dirname=path.dirname(path.abspath(__file__))
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

    return cdk.CustomResource(
        scope, f"{name}_custom", service_token=cdk.Token.as_string(on_event.node.default_child.get_att('Arn'))
    )
