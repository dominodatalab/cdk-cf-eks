#!/usr/bin/env python3

import argparse
from sys import stdout

from json import dumps as json_dumps
from ruamel.yaml import YAML, SafeLoader
from ruamel.yaml import load as yaml_load

from domino_cdk.config import config_loader
from domino_cdk.config.template import config_template
from domino_cdk.config.iam import generate_iam
from domino_cdk.util import DominoCdkUtil

DEFAULT_TF_MODULE_PATH = "https://github.com/dominodatalab/cdk-cf-eks/releases/download/v0.0.1rc1/domino-cdk-terraform-0.0.1rc1.tar.gz"


def parse_args():
    parser = argparse.ArgumentParser(description="domino_cdk utility")
    subparsers = parser.add_subparsers(title="commands")

    template_parser = subparsers.add_parser("generate_config_template", help="Generate Config Template")
    template_parser.add_argument("--name", help="Name for deployment, will prefix all namespaces [defualt: domino]", default="domino")
    template_parser.add_argument("--dev", help="Use development (small) defaults", action="store_true")
    template_parser.add_argument("--bastion", help="Provision bastion", action="store_true")
    template_parser.add_argument("--private-api", help="Use private api with EKS", action="store_true")
    template_parser.add_argument("--no-comments", help="Strip comments from template", action="store_true")
    template_parser.add_argument("--platform-nodegroups", help="How many platform nodegroups per az", default=1, type=int)
    template_parser.add_argument("--compute-nodegroups", help="How many compute nodegroups per az", default=1, type=int)
    template_parser.add_argument("--gpu-nodegroups", help="How many compute nodegroups per az", default=1, type=int)
    template_parser.add_argument("--keypair-name", help="Name of AWS Keypair for bastion/nodegroup SSH [default: None]")
    template_parser.set_defaults(func=generate_config_template)

    iam_parser = subparsers.add_parser("generate_iam_policy", help="Generate IAM Policy for CloudFormation")
    iam_parser.add_argument("-s", "--stack-name", help="Name of CloudFormation stack", default="<YOUR_STACK_NAME>")
    iam_parser.add_argument("-a", "--aws-account-id", help="AWS Account ID", default="<YOUR_ACCOUNT_ID>")
    iam_parser.add_argument("-t", "--terraform", help="IAM Policy for Deploying CloudFormation stack via Terraform", action="store_true")
    iam_parser.set_defaults(func=generate_iam_policy)

    load_parser = subparsers.add_parser("load_config", help="Load config into memory for linting/updating")
    load_parser.add_argument("-f", "--file", help="File to load, otherwise reads stdin", default=None)
    load_parser.add_argument("-o", "--out-file", help="File to write to or '-' for stdout [default: none]", default=None)
    load_parser.add_argument("--no-comments", help="Strip comments from template", action="store_true")
    load_parser.set_defaults(func=load_config)

    asset_parser = subparsers.add_parser("generate_asset_parameters", help="Generate CloudFormation parameters for CDK assets")
    asset_parser.add_argument("-b", "--bucket", help="Name of bucket you plan to upload rendered CDK assets to (optional, default: __FILL__)", default="__FILL__")
    asset_parser.add_argument("-d", "--dir", help="Directory with rendered CDK assets (optional, default: cdk.out)", default="cdk.out")
    asset_parser.set_defaults(func=generate_asset_parameters)

    tf_bootstrap_parser = subparsers.add_parser("generate_terraform_bootstrap", help="Generate Terraform bootstrap config")
    tf_bootstrap_parser.add_argument("-m", "--module-path", help=f"Path to terraform module (optional, default: {DEFAULT_TF_MODULE_PATH})", default=DEFAULT_TF_MODULE_PATH)
    tf_bootstrap_parser.add_argument("-b", "--bucket", help="Path to asset bucket, ie where to upload rendered CDK asset directory (optional, default: __FILL__)", default="__FILL__")
    tf_bootstrap_parser.add_argument("-d", "--dir", help="Directory with rendered CDK assets (optional, default: cdk.out)", default="cdk.out")
    tf_bootstrap_parser.add_argument("-r", "--aws-region", help="AWS Region")
    tf_bootstrap_parser.add_argument("-o", "--output_dir", help="Directory Terraform will write kubeconfig/installer config to")
    tf_bootstrap_parser.add_argument("--disable-random-templates", help="Disable randomly generated template names (used to trigger changes)", action="store_true", default=False)
    tf_bootstrap_parser.add_argument("--iam-role-arn", help="IAM Role to assign to CloudFormation stack (optional, default: none)", default=None)
    tf_bootstrap_parser.set_defaults(func=generate_terraform_bootstrap)

    return parser.parse_args()


def generate_config_template(args):
    YAML().dump(config_template(
        name=args.name,
        platform_nodegroups=args.platform_nodegroups,
        compute_nodegroups=args.compute_nodegroups,
        gpu_nodegroups=args.gpu_nodegroups,
        keypair_name=args.keypair_name,
        bastion=args.bastion,
        private_api=args.private_api,
        dev_defaults=args.dev,
    ).render(args.no_comments), stdout)


def generate_iam_policy(args):
    print(json_dumps(
        generate_iam(
            stack_name=args.stack_name,
            aws_account_id=args.aws_account_id,
            terraform=args.terraform,
        ),
        indent=4,
    ))


def load_config(args):
    print(f"Loading config {args.file or 'from stdin'}...")
    with open(args.file or 0) as f:
        cfg = config_loader(yaml_load(f, Loader=SafeLoader))

    print("Config loaded successfully")

    if args.out_file:
        with open(1 if args.out_file == "-" else args.out_file, "w") as out:
            YAML().dump(cfg.render(args.no_comments), out)


def generate_asset_parameters(args):
    print(json_dumps(
        DominoCdkUtil.generate_asset_parameters(args.dir, args.bucket),
        indent=4,
    ))


def generate_terraform_bootstrap(args):
    print(json_dumps(
        DominoCdkUtil.generate_terraform_bootstrap(args.module_path, args.bucket, args.dir, args.aws_region, args.output_dir, args.disable_random_templates, args.iam_role_arn),
        indent=4,
    ))


if __name__ == "__main__":
    args = parse_args()

    args.func(args)
