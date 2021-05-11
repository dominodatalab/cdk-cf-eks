#!/usr/bin/env python3
import os
from json import dumps as json_dumps
from sys import argv
import yaml
from aws_cdk import core

from domino.domino_stack import DominoStack

with open("config.yaml") as f:
    y = f.read()
    cfg = yaml.safe_load(y)

app = core.App(context={"config": cfg})

env_vars = {}

DominoStack(
    app,
    f"{cfg['name']}-domino-eks-stack",
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
    env=core.Environment(region=cfg.get("aws_region"), account=cfg.get("aws_account_id", None)),
)


if __name__ == "__main__":
    if len(argv) > 1:
        if argv[1] == "generate_asset_parameters":
            print(json_dumps(DominoStack.generate_asset_parameters(*argv[2:]), indent=4))
        elif argv[1] == "generate_terraform_bootstrap":
            print(json_dumps(DominoStack.generate_terraform_bootstrap(*argv[2:]), indent=4))
        else:
            print("Valid utility commands are 'generate_asset_parameters' and 'generate_terraform_bootstrap'. Otherwise, use cdk.")
            exit(1)
    app.synth()
