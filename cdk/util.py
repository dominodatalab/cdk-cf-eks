#!/usr/bin/env python3

import argparse
from json import dumps as json_dumps
from sys import stdout

from ruamel.yaml import YAML, SafeLoader
from ruamel.yaml import load as yaml_load

from domino_cdk.config import config_loader
from domino_cdk.config.iam import generate_iam
from domino_cdk.config.template import config_template
from domino_cdk.util import DominoCdkUtil

DEFAULT_TF_MODULE_PATH = (
    "https://github.com/dominodatalab/cdk-cf-eks/releases/download/v0.0.1rc2/domino-cdk-terraform-0.0.1-rc2.tar.gz"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="domino_cdk utility", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(title="commands")

    template_parser = subparsers.add_parser(
        "generate_config_template",
        help="Generate Config Template",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    template_parser.add_argument("--name", help="Name for deployment, will prefix all namespaces", default="domino")
    template_parser.add_argument("--aws-region", help="AWS Region", default=None)
    template_parser.add_argument("--aws-account-id", help="AWS Account ID", default=None)
    template_parser.add_argument("--dev", help="Use development (small) defaults", action="store_true")
    template_parser.add_argument("--bastion", help="Provision bastion", action="store_true")
    template_parser.add_argument("--private-api", help="Use private api with EKS", action="store_true")
    template_parser.add_argument("--istio-compatible", help="Provision istio-compatible resources", action="store_true")
    template_parser.add_argument("--no-comments", help="Strip comments from template", action="store_true")
    template_parser.add_argument(
        "--platform-nodegroups", help="How many platform nodegroups per az", default=1, type=int
    )
    template_parser.add_argument("--compute-nodegroups", help="How many compute nodegroups per az", default=1, type=int)
    template_parser.add_argument("--gpu-nodegroups", help="How many compute nodegroups per az", default=1, type=int)
    template_parser.add_argument("--keypair-name", help="Name of AWS Keypair for bastion/nodegroup SSH", default=None)
    template_parser.add_argument(
        "--secrets-encryption-key-arn",
        help="KMS Key arn to encrypt kubernetes secrets, generated if not provided",
        default=None,
    )
    template_parser.add_argument("--registry-username", help="Quay.io Registry Username", default=None)
    template_parser.add_argument("--registry-password", help="Quay.io Registry Password", default=None)
    template_parser.add_argument("--acm-cert-arn", help="ACM Cert ARN", default="__FILL__")
    template_parser.add_argument(
        "--hostname", help="Hostname for deployment (ie domino.example.com)", default="__FILL__"
    )
    template_parser.add_argument(
        "--disable-flow-logs", help="Disable monitoring bucket (temporary option)", action="store_true", default=False
    )
    template_parser.set_defaults(func=generate_config_template)

    iam_parser = subparsers.add_parser(
        "generate_iam_policies",
        help="Generate IAM Policies for CloudFormation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    iam_parser.add_argument("-s", "--stack-name", help="Name of CloudFormation stack", default="<YOUR_STACK_NAME>")
    iam_parser.add_argument("-a", "--aws-account-id", help="AWS Account ID", default="<YOUR_ACCOUNT_ID>")
    iam_parser.add_argument("-r", "--region", help="AWS region", default="<YOUR_REGION>")
    iam_parser.add_argument(
        "-m", "--manual", help="Use policy geared toward manual or terraform deployments", action="store_true"
    )
    iam_parser.add_argument(
        "-o",
        "--out-file-base",
        help="Base filename (ie 'iam-policy' for 'iam-policy-1/2/3.json'). All files generated are printed to stdout.",
        default="deploy-policy",
    )
    iam_parser.add_argument("-b", "--bastion", help="Add ec2 perms for bastion", action="store_true", default=False)
    iam_parser.set_defaults(func=generate_iam_policies)

    load_parser = subparsers.add_parser(
        "load_config",
        help="Load config into memory for linting/updating",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    load_parser.add_argument("-f", "--file", help="File to load, otherwise reads stdin", default=None)
    load_parser.add_argument("-o", "--out-file", help="File to write to or '-' for stdout", default=None)
    load_parser.add_argument("--no-comments", help="Strip comments from template", action="store_true")
    load_parser.set_defaults(func=load_config)

    asset_parser = subparsers.add_parser(
        "generate_asset_parameters",
        help="Generate CloudFormation parameters for CDK assets",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    asset_parser.add_argument(
        "-b",
        "--bucket",
        help="Name of bucket you plan to upload rendered CDK assets to",
        default="__FILL__",
    )
    asset_parser.add_argument("-d", "--dir", help="Directory with rendered CDK assets (optional)", default="cdk.out")
    asset_parser.set_defaults(func=generate_asset_parameters)

    tf_bootstrap_parser = subparsers.add_parser(
        "generate_terraform_bootstrap",
        help="Generate Terraform bootstrap config",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    tf_bootstrap_parser.add_argument(
        "-m",
        "--module-path",
        help="Path to terraform module (optional)",
        default=DEFAULT_TF_MODULE_PATH,
    )
    tf_bootstrap_parser.add_argument(
        "-b",
        "--bucket",
        help="Path to asset bucket, ie where to upload rendered CDK asset directory (optional)",
        default="__FILL__",
    )
    tf_bootstrap_parser.add_argument(
        "-d", "--dir", help="Directory with rendered CDK assets (optional)", default="cdk.out"
    )
    tf_bootstrap_parser.add_argument("-r", "--aws-region", help="AWS Region")
    tf_bootstrap_parser.add_argument(
        "-o", "--output_dir", help="Directory Terraform will write kubeconfig/installer config to"
    )
    tf_bootstrap_parser.add_argument(
        "--disable-random-templates",
        help="Disable randomly generated template names (used to trigger changes)",
        action="store_true",
        default=False,
    )
    tf_bootstrap_parser.add_argument(
        "--iam-role-arn", help="IAM Role to assign to CloudFormation stack (optional)", default=None
    )
    tf_bootstrap_parser.add_argument(
        "--iam-policy-path",
        help="IAM policy file(s) to provision and attach to role and assign to CloudFormation stack. Can be specified multiple times for multiple policies.  (optional)",
        action="append",
        default=[],
    )
    tf_bootstrap_parser.set_defaults(func=generate_terraform_bootstrap)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        exit(0)

    return args


def generate_config_template(args):
    YAML().dump(
        config_template(
            name=args.name,
            aws_region=args.aws_region,
            aws_account_id=args.aws_account_id,
            platform_nodegroups=args.platform_nodegroups,
            compute_nodegroups=args.compute_nodegroups,
            gpu_nodegroups=args.gpu_nodegroups,
            keypair_name=args.keypair_name,
            secrets_encryption_key_arn=args.secrets_encryption_key_arn,
            bastion=args.bastion,
            private_api=args.private_api,
            dev_defaults=args.dev,
            istio_compatible=args.istio_compatible,
            registry_username=args.registry_username,
            registry_password=args.registry_password,
            acm_cert_arn=args.acm_cert_arn,
            hostname=args.hostname,
            disable_flow_logs=args.disable_flow_logs,
        ).render(args.no_comments),
        stdout,
    )


def generate_iam_policies(args):
    policies = generate_iam(
        stack_name=args.stack_name,
        aws_account_id=args.aws_account_id,
        region=args.region,
        manual=args.manual,
        use_bastion=args.bastion,
    )

    for i, policy in enumerate(policies):
        fn = f"{args.out_file_base}-{i}.json"
        with open(fn, "w") as out:
            out.write(f"{json_dumps(policy, indent=4)}\n")
            print(fn)


def load_config(args):
    print(f"Loading config {args.file or 'from stdin'}...")
    with open(args.file or 0) as f:
        cfg = config_loader(yaml_load(f, Loader=SafeLoader))

    print("Config loaded successfully")

    if args.out_file:
        with open(1 if args.out_file == "-" else args.out_file, "w") as out:
            YAML().dump(cfg.render(args.no_comments), out)


def generate_asset_parameters(args):
    print(
        json_dumps(
            DominoCdkUtil.generate_asset_parameters(args.dir, args.bucket),
            indent=4,
        )
    )


def generate_terraform_bootstrap(args):
    if args.iam_role_arn and args.iam_policy_path:
        raise Exception("Cannot provide both --iam-role-arn and --iam-policy-path!")
    print(
        json_dumps(
            DominoCdkUtil.generate_terraform_bootstrap(
                args.module_path,
                args.bucket,
                args.dir,
                args.aws_region,
                args.output_dir,
                args.disable_random_templates,
                args.iam_role_arn,
                args.iam_policy_path,
            ),
            indent=4,
        )
    )


if __name__ == "__main__":
    args = parse_args()

    args.func(args)
