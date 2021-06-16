#!/usr/bin/env python3
from json import dumps as json_dumps
from sys import argv, stdout

from aws_cdk import core
from ruamel.yaml import YAML, SafeLoader
from ruamel.yaml import load as yaml_load

from domino_cdk.config import config_loader, config_template
from domino_cdk.domino_stack import DominoStack
from domino_cdk.util import DominoCdkUtil


def main():
    app = core.App()

    with open(app.node.try_get_context("config") or "config.yaml") as f:
        cfg = config_loader(yaml_load(f, Loader=SafeLoader))

    nest = app.node.try_get_context("nest") or False

    DominoStack(
        app,
        f"{cfg.name}-eks-stack",
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


if __name__ == "__main__":
    if len(argv) > 1:
        if argv[1] == "generate_asset_parameters":
            print(json_dumps(DominoCdkUtil.generate_asset_parameters(*argv[2:]), indent=4))
        elif argv[1] == "generate_terraform_bootstrap":
            print(json_dumps(DominoCdkUtil.generate_terraform_bootstrap(*argv[2:]), indent=4))
        elif argv[1] == "generate_config_template":
            YAML().dump(config_template().render(*argv[2:]), stdout)  # an arg disable comments
        else:
            print(
                "Valid utility commands are 'generate_asset_parameters', 'generate_terraform_bootstrap' and 'generate_config_template'. Otherwise, use cdk."
            )
            exit(1)
        exit(0)
    main()
