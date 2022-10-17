from os import path
from typing import Any, Dict, List, Optional

import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_logs as logs
from constructs import Construct


def create_lambda(
    scope: Construct,
    stack_name: str,
    name: str,
    resources: List[str],
    actions: List[str],
    properties: Optional[Dict[str, Any]] = None,
    environment: Optional[Dict[str, Any]] = None,
) -> Construct:
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

    return cdk.CustomResource(scope, f"{name}_custom", service_token=on_event.function_arn, properties=properties)
