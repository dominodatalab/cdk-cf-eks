#!/usr/bin/env python3
from aws_cdk import core
from ruamel.yaml import SafeLoader
from ruamel.yaml import load as yaml_load

from domino_cdk.config import config_loader
from domino_cdk.domino_stack import DominoStack


app = core.App()

with open(app.node.try_get_context("config") or "config.yaml") as f:
    cfg = config_loader(yaml_load(f, Loader=SafeLoader))

nest = app.node.try_get_context("singlestack") or True

DominoStack(
    app,
    f"{cfg.name}",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.
    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.
    # env=core.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */
    # env=core.Environment(account='123456789012', region='us-east-1'),
    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    env=core.Environment(region=cfg.aws_region, account=cfg.aws_account_id),
    cfg=cfg,
    nest=nest,
)

app.synth()
