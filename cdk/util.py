#!/usr/bin/env python3

import argparse
from sys import stdout

from ruamel.yaml import YAML

from domino_cdk.config import config_template

def parse_args():
    parser = argparse.ArgumentParser(description="domino_cdk utility")
    subparsers = parser.add_subparsers(title="commands")

    template_parser = subparsers.add_parser("generate_config_template", help="Generate Config Template")
    template_parser.add_argument("--dev", help="Use development (small) defaults", action="store_true")
    template_parser.add_argument("--bastion", help="Provision bastion", action="store_true")
    template_parser.add_argument("--private-api", help="Use private api with EKS", action="store_true")
    template_parser.add_argument("--no-comments", help="Strip comments from template", action="store_true")
    template_parser.add_argument("--platform-nodegroups", help="How many platform nodegroups", default=3, type=int)
    template_parser.add_argument("--compute-nodegroups", help="How many compute nodegroups", default=3, type=int)
    template_parser.add_argument("--gpu-nodegroups", help="How many compute nodegroups", default=3, type=int)
    template_parser.set_defaults(func=generate_config_template)

    return parser.parse_args()

def generate_config_template(args):
    YAML().dump(config_template(
        platform_nodegroups=args.platform_nodegroups,
        compute_nodegroups=args.compute_nodegroups,
        gpu_nodegroups=args.gpu_nodegroups,
        bastion=args.bastion,
        private_api=args.private_api,
        dev_defaults=args.dev,
    ).render(args.no_comments), stdout)

if __name__ == "__main__":
    args = parse_args()

    args.func(args)
