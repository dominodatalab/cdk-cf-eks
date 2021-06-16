#!/usr/bin/env python3

import argparse
from sys import stdout

from ruamel.yaml import YAML, SafeLoader
from ruamel.yaml import load as yaml_load

from domino_cdk.config import config_loader
from domino_cdk.config.template import config_template

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
    template_parser.set_defaults(func=generate_config_template)

    load_parser = subparsers.add_parser("load_config", help="Load config into memory for linting/updating")
    load_parser.add_argument("-f", "--file", help="File to load, otherwise reads stdin", default=None)
    load_parser.add_argument("-o", "--out-file", help="File to write to or '-' for stdout [default: none]", default=None)
    load_parser.add_argument("--no-comments", help="Strip comments from template", action="store_true")
    load_parser.set_defaults(func=load_config)

    return parser.parse_args()

def generate_config_template(args):
    YAML().dump(config_template(
        name=args.name,
        platform_nodegroups=args.platform_nodegroups,
        compute_nodegroups=args.compute_nodegroups,
        gpu_nodegroups=args.gpu_nodegroups,
        bastion=args.bastion,
        private_api=args.private_api,
        dev_defaults=args.dev,
    ).render(args.no_comments), stdout)

def load_config(args):
    print(f"Loading config {args.file or 'from stdin'}...")
    with open(args.file or 0) as f:
        cfg = config_loader(yaml_load(f, Loader=SafeLoader))

    print("Config loaded successfully")

    if args.out_file:
        with open(1 if args.out_file == "-" else args.out_file, "w") as out:
            YAML().dump(cfg.render(args.no_comments), out)

if __name__ == "__main__":
    args = parse_args()

    args.func(args)
