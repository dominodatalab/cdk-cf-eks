#!/usr/bin/env python3
import argparse
import json
import re
from copy import deepcopy
from functools import cached_property, reduce
from os.path import abspath
from pprint import pprint
from subprocess import run
from time import sleep

import boto3
import yaml

from .meta import (
    bastion_resources,
    cdk_ids,
    cf_status,
    efs_backup_resources,
    monitoring_bucket_resource,
    resource_template,
    route53_resource,
    stack_map,
)
from .nuke import nuke

clean_categories = [x.name for x in cdk_ids if x.name != "cloudformation_stack"]


class app:
    def __init__(self):
        self.parse_args()
        self.args.command()

    def get_stacks(self, stack: str = None, full: bool = False):
        stacks = {"resources": {}}
        p = self.cf.get_paginator("list_stack_resources")
        resources = [
            summary for i in p.paginate(StackName=stack or self.stack_name) for summary in i["StackResourceSummaries"]
        ]
        for r in resources:
            logical_id = r["LogicalResourceId"]
            physical_id = r["PhysicalResourceId"]
            if r["ResourceType"] == cdk_ids.cloudformation_stack.value:
                for mapped_logical_id, name in stack_map.items():
                    if logical_id.startswith(mapped_logical_id):
                        stacks[name] = self.get_stacks(physical_id, full)
                        break
                else:
                    raise Exception(f"Nothing to map stack {r} to!")
            else:
                parsed_logical_id = logical_id[:-8] if re.match("^[0-9A-F]{8}", logical_id[-8:]) else logical_id
                stacks["resources"][parsed_logical_id] = r if full else physical_id
        return stacks

    def setup(self, full: bool = False, no_stacks: bool = False):
        self.region = self.args.region
        self.stack_name = self.args.stack_name
        self.cf_stack_key = re.sub(r"\W", "", self.stack_name)

        self.cf = boto3.client("cloudformation", self.region)

        if not no_stacks:
            self.sanity()
            self.stacks = self.get_stacks(full=full)

    @cached_property
    def cdkconfig(self):
        return yaml.safe_load(
            [
                o["OutputValue"]
                for o in self.cf.describe_stacks(StackName=self.stack_name)["Stacks"][0]["Outputs"]
                if o["OutputKey"] == "cdkconfig"
            ][0]
        )

    def sanity(self):
        p = self.cf.get_paginator("list_stacks")
        stacks = [
            ss
            for i in p.paginate(StackStatusFilter=[s for s in cf_status if s != "DELETE_COMPLETE"])
            for ss in i["StackSummaries"]
            if ss["StackName"] == self.stack_name
        ]

        if len(stacks) > 1:
            print(f"Multiple stacks named {self.stack_name}, bailing...")
            exit(1)
        elif len(stacks) == 0:
            print(f"No live stacks named {self.stack_name}, stack already deleted?")
            exit(0)

    def parse_args(self):
        parser = argparse.ArgumentParser(
            description="terraform eks module importer",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )

        subparsers = parser.add_subparsers(title="commands")

        common_parser = argparse.ArgumentParser(add_help=False)
        common_parser.add_argument("--region", help="AWS Region", required=True)
        common_parser.add_argument("--stack-name", help="Name of stack", required=True)

        create_tfvars_parser = subparsers.add_parser(
            name="create-tfvars", help="Generate tfvars", parents=[common_parser]
        )
        create_tfvars_parser.add_argument("--ssh-key-path", help="Path to local SSH key to cluster", required=True)
        create_tfvars_parser.set_defaults(command=self.create_tfvars)

        resource_map_parser = subparsers.add_parser(
            name="resource-map",
            help="Create resource map for customization/debugging of get-imports command (optional step)",
        )
        resource_map_parser.add_argument("--availability-zones", help="Availability zone count", default=3, type=int)
        resource_map_parser.add_argument(
            "--route53", help="Whether or not to import route53 zones", default=False, action="store_true"
        )
        resource_map_parser.add_argument(
            "--bastion", help="Whether or not to import bastion security group", default=False, action="store_true"
        )
        resource_map_parser.add_argument(
            "--monitoring", help="Whether or not to import monitoring bucket", default=False, action="store_true"
        )
        resource_map_parser.add_argument(
            "--efs-backups",
            help="Whether or not to import efs backup vault",
            default=True,
            action=argparse.BooleanOptionalAction,
        )
        resource_map_parser.set_defaults(command=self.resource_map)

        import_parser = subparsers.add_parser(
            name="get-imports", help="Get terraform import commands", parents=[common_parser]
        )
        import_parser.add_argument(
            "--availability-zones",
            help="Availability zone count override. Default: autodetect from cdk config; no effect when using a resource map",
            default=None,
            type=int,
        )
        import_parser.add_argument(
            "--resource-map", help="Path to custom resource map file (otherwise, we autoconfigure)", default=None
        )
        import_parser.set_defaults(command=self.get_imports)

        clean_stack_parser = subparsers.add_parser(
            name="clean-stack", help="Clean stack something something", parents=[common_parser]
        )
        clean_stack_parser.add_argument(
            "--delete", help="Delete unneeded stack items", default=False, action="store_true"
        )
        clean_stack_parser.add_argument(
            "--all-staged-resources",
            help="Print all potentially deleteable resources from stack, without checking if they exist",
            default=False,
            action="store_true",
        )
        clean_stack_parser.add_argument(
            "--include-types",
            help=f"Only processes specified categories: {clean_categories}",
            type=lambda s: [x.strip() for x in s.split(",")],
        )
        clean_stack_parser.add_argument(
            "--resource-file",
            help="Load resources from yaml file generated via --print-stack --verbose --yaml; useful if stack is gone",
        )
        clean_stack_parser.add_argument(
            "--remove-security-group-references",
            help="Remove rules referencing security groups to be deleted. Otherwise, prints offending groups for manual deletion.",
            default=False,
            action="store_true",
        )
        clean_stack_parser.add_argument("--verbose", help="Verbose logging", default=False, action="store_true")
        clean_stack_parser.set_defaults(command=self.clean_stack)

        delete_stack_parser = subparsers.add_parser(
            name="delete-stack", help="Get commands to delete old stack", parents=[common_parser]
        )
        delete_stack_parser.add_argument(
            "--delete", help="Delete unneeded stack items", default=False, action="store_true"
        )
        delete_stack_parser.set_defaults(command=self.delete_stack)

        print_stack_parser = subparsers.add_parser(
            name="print-stack", help="Print CDK stack resources", parents=[common_parser]
        )
        print_stack_parser.add_argument(
            "--sub-stack", help=f"Sub-stacks to print, can be any of {stack_map.values()}", default=None
        )
        print_stack_parser.add_argument(
            "--verbose", help="Print verbose stack info", default=False, action="store_true"
        )
        print_stack_parser.add_argument("--yaml", help="Output as YAML", default=False, action="store_true")
        print_stack_parser.set_defaults(command=self.print_stack)

        self.args = parser.parse_args()

        if not getattr(self.args, "command", None):
            parser.print_help()
            exit(0)

    def print_stack(self):
        self.setup(full=self.args.verbose)
        out = self.stacks[self.args.sub_stack] if self.args.sub_stack else self.stacks
        if self.args.yaml:
            print(yaml.safe_dump(out))
        else:
            pprint(out)

    def generate_resource_map(
        self, availability_zones: int, efs_backups: bool, route53: bool, bastion: bool, monitoring: bool
    ) -> dict:
        template = deepcopy(resource_template)
        for count in range(availability_zones):
            template["efs_stack"].append(
                {
                    "cf": f"EfsEfsMountTarget{count+1}",
                    "tf": f"module.domino_eks.module.storage.aws_efs_mount_target.eks[{count}]",
                }
            )
            for s_type in ["Public", "Private", "Pod"]:
                vpc_prefix = "" if s_type == "Pod" else "VPC"
                prefix = f"{vpc_prefix}%cf_stack_key%{s_type}Subnet{count+1}"
                template["vpc_stack"].extend(
                    [
                        {
                            "cf": f"{prefix}Subnet",
                            "tf": f"aws_subnet.{s_type.lower()}[{count}]",
                        },
                        {
                            "cf": f"{prefix}RouteTable",
                            "tf": f"aws_route_table.{s_type.lower()}[{count}]",
                        },
                        {
                            "cf_rtassoc": {
                                "subnet": f"{prefix}Subnet",
                                "route_table": f"{prefix}RouteTable",
                            },
                            "tf": f"aws_route_table_association.{s_type.lower()}[{count}]",
                        },
                    ]
                )
            template["vpc_stack"].extend(
                [
                    {
                        "cf": f"VPC%cf_stack_key%PublicSubnet{count+1}EIP",
                        "tf": f"aws_eip.nat_gateway[{count}]",
                    },
                    {
                        "cf": f"VPC%cf_stack_key%PublicSubnet{count+1}NATGateway",
                        "tf": f"aws_nat_gateway.public[{count}]",
                    },
                ]
            )

        if efs_backups:
            template["efs_stack"].extend(efs_backup_resources)

        if route53:
            template["eks_stack"].append(route53_resource)

        if monitoring:
            template["s3_stack"].append(monitoring_bucket_resource)

        if bastion:
            template["eks_stack"].extend(bastion_resources["eks_stack"])
            template["vpc_stack"].extend(bastion_resources["vpc_stack"])

        return template

    def resource_map(self):
        resource_map = self.generate_resource_map(
            self.args.availability_zones,
            self.args.efs_backups,
            self.args.route53,
            self.args.bastion,
            self.args.monitoring,
        )
        print(yaml.safe_dump(resource_map))

    def get_imports(self):
        self.setup()

        if self.args.resource_map:
            with open(self.args.resource_map) as f:
                resource_map = yaml.safe_load(f)
        else:
            resource_map = self.generate_resource_map(
                availability_zones=self.args.availability_zones or self.cdkconfig["vpc"]["max_azs"],
                efs_backups=self.cdkconfig["efs"]["backup"]["enable"],
                route53=bool(self.cdkconfig["route53"]["zone_ids"]),
                bastion=self.cdkconfig["vpc"]["bastion"]["enabled"],
                monitoring=self.cdkconfig["s3"]["buckets"].get("monitoring"),
            )

        def t(val: str) -> str:
            val = re.sub(r"%stack_name%", self.stack_name, val)
            val = re.sub(r"%cf_stack_key%", self.cf_stack_key, val)
            return val

        imports = []

        for map_stack, items in resource_map.items():
            resources = self.stacks[map_stack]["resources"]
            for item in items:
                tf_import_path = t(item["tf"])
                if value := item.get("value"):
                    resource_id = t(value)
                elif cf_sgr := item.get("cf_sgr"):
                    sg = resources[t(cf_sgr["sg"])]
                    append_rule_sg = ""
                    if rule_sg := cf_sgr.get("rule_sg"):
                        rule_sg_r = resources
                        if rule_sg_stack := cf_sgr.get("rule_sg_stack"):
                            rule_sg_r = self.stacks[t(rule_sg_stack)]["resources"]
                        append_rule_sg = rule_sg_r[t(rule_sg)]
                    resource_id = f"{sg}{t(cf_sgr['rule'])}{append_rule_sg}"
                elif cf_igw_attachment := item.get("cf_igw_attachment"):
                    igw_id = resources[t(cf_igw_attachment["igw"])]
                    vpc_id = resources[t(cf_igw_attachment["vpc"])]
                    resource_id = f"{igw_id}:{vpc_id}"
                elif assoc := item.get("cf_rtassoc"):
                    resource_id = f"{resources[t(assoc['subnet'])]}/{resources[t(assoc['route_table'])]}"
                elif bkpsel := item.get("cf_backupselection"):
                    selection_id, plan_id = resources[t(bkpsel)].split("_")
                    resource_id = f"{plan_id}|{selection_id}"
                else:
                    resource_id = resources[t(item["cf"])]
                imports.append(f"terraform import '{tf_import_path}' '{resource_id}'")

        print("#!/bin/bash\nset -ex")
        print("\n".join(imports))

    def create_tfvars(self):
        self.setup()

        def get_subnet_ids(subnet_type: str, prefix: str = "VPC"):
            return [
                v
                for k, v in self.stacks["vpc_stack"]["resources"].items()
                if re.match(f"{prefix}{self.cf_stack_key}{subnet_type}Subnet\\d+Subnet", k)
            ]

        ng_role_name = self.stacks["eks_stack"]["resources"][f"{self.cf_stack_key}NG"]
        client = boto3.client("iam", self.region)
        ng_role_arn = client.get_role(RoleName=ng_role_name)["Role"]["Arn"]
        eks_custom_role_maps = [
            {
                "rolearn": ng_role_arn,
                "username": "system:node:{{EC2PrivateDNSName}}",
                "groups": [
                    "system:masters",
                    "system:bootstrappers",
                    "system:nodes",
                ],
            }
        ]

        tfvars = {
            "deploy_id": self.cdkconfig["name"],
            "region": self.cdkconfig["aws_region"],
            "grandfathered_creation_role": self.stacks["eks_stack"]["resources"]["eksCreationRole"],
            "tags": {**self.cdkconfig["tags"], "domino-deploy-id": self.cdkconfig["name"]},
            "vpc_id": self.cdkconfig["vpc"]["id"]
            if not self.cdkconfig["vpc"]["create"]
            else self.stacks["vpc_stack"]["resources"]["VPC"],
            "public_subnet_ids": get_subnet_ids("Public"),
            "private_subnet_ids": get_subnet_ids("Private"),
            "pod_subnet_ids": get_subnet_ids("Pod", ""),
            "k8s_version": self.cdkconfig["eks"]["version"],  # We're trusting this is accurate
            "ssh_key_path": abspath(self.args.ssh_key_path),
            "number_of_azs": self.cdkconfig["vpc"]["max_azs"],
            "route53_hosted_zone_name": reduce(
                lambda cfg, k: cfg[k] if k in cfg else [""],
                ["install", "overrides", "external_dns", "domain_filters"],
                self.cdkconfig,
            )[0],
            "efs_backups": self.cdkconfig["efs"]["backup"]["enable"],
            "efs_backup_schedule": self.cdkconfig["efs"]["backup"]["schedule"],
            "efs_backup_cold_storage_after": self.cdkconfig["efs"]["backup"]["move_to_cold_storage_after"],
            "efs_backup_delete_after": self.cdkconfig["efs"]["backup"]["delete_after"],
            "efs_backup_force_destroy": self.cdkconfig["efs"]["backup"]["removal_policy"] == "DESTROY",
            "eks_custom_role_maps": eks_custom_role_maps,
        }

        print(json.dumps(tfvars))

        if not self.cdkconfig["eks"]["private_api"]:
            print(
                "*** IMPORTANT ***: Your CDK EKS is configured for public API access.\n"
                "Your cluster's setting will be changed to *PRIVATE*, as the terraform\n"
                "module does not support public EKS endpoints."
            )

    def clean_stack(self):
        self.setup(full=True, no_stacks=self.args.resource_file)

        if self.args.resource_file:
            with open(self.args.resource_file) as f:
                self.stacks = yaml.safe_load(f.read())

        include_types = self.args.include_types or clean_categories

        for t in include_types:
            if t not in clean_categories:
                raise ValueError(f"{t} not a valid category for `--include-types`. Should be: {clean_categories}")

        lambda_safe = [
            cdk_ids.lambda_function.value,
            cdk_ids.iam_role.value,
            cdk_ids.lambda_layerversion.value,
            cdk_ids.stepfunctions_statemachine.value,
        ]
        nukey = {
            "efs_stack": {
                "(LogRetention|backuppostcreationtasks).*": lambda_safe,
            },
            "eks_cluster_stack": {
                "(LogRetention|IsCompleteHandler|NodeProxyAgentLayer|OnEventHandler|Provider).*": lambda_safe,
            },
            "eks_kubectl_stack": {
                "(Handler|KubectlLayer|ProviderframeworkonEvent).*": lambda_safe,
            },
            "eks_stack": {
                f"(snapshot|{self.cf_stack_key}ebscsi|{self.cf_stack_key}DominoEcrRestricted|autoscaler)": [
                    cdk_ids.iam_policy.value
                ],
                f"(eksMastersRole|{self.cf_stack_key}NG)$": [cdk_ids.iam_role.value],
                "eksKubectlReadyBarrier": [cdk_ids.ssm_parameter.value],
                "(clusterpost(creation|deletion)tasks|LogRetention)": lambda_safe,
                "Unmanaged": [cdk_ids.instance_profile.value, cdk_ids.asg.value, cdk_ids.launch_template.value],
            },
            "s3_stack": {
                "CustomS3AutoDeleteObjectsCustomResourceProvider": lambda_safe,
            },
            "vpc_stack": {
                "endpointssg": [cdk_ids.security_group.value],
                "bastion": [
                    cdk_ids.instance.value,
                    cdk_ids.instance_profile.value,
                    cdk_ids.iam_role.value,
                    cdk_ids.eip.value,
                ],
                "VPCrejectFlowLogsFlowLog": [cdk_ids.flowlog.value],  # TODO: should this be in the module?
                "(LogRetention|AWS)": lambda_safe,
            },
            "core_stack": {
                "(LogRetention|fixmissingtags)": lambda_safe,
            },
        }

        nuke_queue = {x.value: [] for x in cdk_ids if x.name in include_types}

        def get_nukes(stack_name, stack_resources):
            for k, v in stack_resources.items():
                for nukey_regex in nukey[stack_name].keys():
                    if (
                        re.match(nukey_regex, k)
                        and v["ResourceType"] in nukey[stack_name][nukey_regex]
                        and v["ResourceType"] in nuke_queue
                    ):
                        nuke_queue[v["ResourceType"]].append(v["PhysicalResourceId"])

        get_nukes("efs_stack", self.stacks["efs_stack"]["resources"])
        get_nukes("eks_cluster_stack", self.stacks["eks_stack"]["cluster_stack"]["resources"])
        get_nukes("eks_kubectl_stack", self.stacks["eks_stack"]["kubectl_stack"]["resources"])
        get_nukes("eks_stack", self.stacks["eks_stack"]["resources"])
        get_nukes("s3_stack", self.stacks["s3_stack"]["resources"])
        get_nukes("vpc_stack", self.stacks["vpc_stack"]["resources"])
        get_nukes("core_stack", self.stacks["resources"])

        # I don't like doing this outside of nuke or making aws calls at this stage
        # but the eks cluster security group isn't gettable from cloudformation...
        ec2 = boto3.client("ec2", self.region)
        eks = boto3.client("eks", self.region)
        eks_cluster_sg = eks.describe_cluster(name=self.stack_name)["cluster"]["resourcesVpcConfig"][
            "clusterSecurityGroupId"
        ]
        unmanaged_sg = self.stacks["eks_stack"]["resources"]["UnmanagedSG"]["PhysicalResourceId"]
        eks_sg = self.stacks["eks_stack"]["resources"]["EKSSG"]["PhysicalResourceId"]

        rule_ids_to_nuke = {
            eks_cluster_sg: {"egress": [], "ingress": []},
            unmanaged_sg: {"egress": [], "ingress": []},
            eks_sg: {"egress": [], "ingress": []},
        }

        for group in rule_ids_to_nuke.keys():
            rules = [
                r
                for r in ec2.describe_security_group_rules(Filters=[{"Name": "group-id", "Values": [group]}])[
                    "SecurityGroupRules"
                ]
                if re.match(f"(from|to) {self.cf_stack_key}", r.get("Description", ""))
            ]
            rule_ids_to_nuke[group]["ingress"].extend([r["SecurityGroupRuleId"] for r in rules if not r["IsEgress"]])
            rule_ids_to_nuke[group]["egress"].extend([r["SecurityGroupRuleId"] for r in rules if r["IsEgress"]])

        nuke_queue[cdk_ids.security_group_rule_ids.value] = rule_ids_to_nuke

        if self.args.all_staged_resources:
            pprint(nuke_queue)
            exit(0)

        nuke(region=self.region, verbose=self.args.verbose, delete=self.args.delete).nuke(
            nuke_queue, self.args.remove_security_group_references
        )

    def delete_stack(self):
        self.setup()

        cf_tf_output = json.loads(
            run(["terraform", "output", "-json"], cwd="cloudformation-only", capture_output=True).stdout
        )
        if not (cf_only_role := cf_tf_output.get("cloudformation_only_role")) or not re.match(
            "arn:.*:iam:.*role/cloudformation-only", cf_only_role["value"]
        ):
            print("Please run the terraform module in the 'cloudformation-only' subdirectory...")
            exit(1)

        if self.args.delete:
            self.cf.delete_stack(StackName=self.stack_name, RoleARN=cf_only_role["value"])

            while True:
                desc_output = self.cf.describe_stacks(StackName=self.stack_name)
                status = desc_output["Stacks"][0]["StackStatus"]
                if status == "DELETE_IN_PROGRESS":
                    sleep(5)
                elif status == "DELETE_FAILED":
                    break

        root_resources = self.cf.describe_stack_resources(StackName=self.stack_name)["StackResources"]

        stacks = {
            self.stack_name: [
                r["LogicalResourceId"] for r in root_resources if r["ResourceStatus"] != "DELETE_COMPLETE"
            ]
        }

        def get_stack_resources(s) -> dict:
            child_id = s["PhysicalResourceId"]
            child_name = re.search(r":stack/(.*)/", child_id).group(1)
            if self.cf.describe_stacks(StackName=child_id)["Stacks"][0]["StackStatus"] == "DELETE_COMPLETE":
                return
            child_resources = self.cf.describe_stack_resources(StackName=child_name)["StackResources"]
            stacks[child_name] = [
                r["LogicalResourceId"] for r in child_resources if r["ResourceStatus"] != "DELETE_COMPLETE"
            ]
            for r in child_resources:
                if r["ResourceType"] == cdk_ids.cloudformation_stack.value:
                    get_stack_resources(r)

        for s in root_resources:
            if s["ResourceType"] == cdk_ids.cloudformation_stack.value:
                get_stack_resources(s)

        for i, (stack, resources) in enumerate(stacks.items()):
            if self.args.delete:
                self.cf.delete_stack(StackName=stack, RoleARN=cf_only_role["value"], RetainResources=resources)
            else:
                if i == 0:
                    print(
                        "Manual instructions:\nFirst run this delete-stack command using the cloudformation-only role:\n"
                    )
                    print(
                        f"aws cloudformation delete-stack --region {self.region} --stack-name {stack} --role {cf_only_role['value']}\n"
                    )
                    print(
                        "This will *attempt* to delete the entire CDK stack, but *intentionally fail* so as to leave the stack in the delete failed state, with all resources having failed. This opens the gate to retain every resource, so the following runs can delete the stack(s) and only the stack(s). After running the first command, rerun this and then execute the following to safely delete the stacks:\n"
                    )
                print(
                    f"aws cloudformation delete-stack --region {self.region} --stack-name {stack} --retain-resources {' '.join(resources)} --role {cf_only_role['value']}\n"
                )

        if not self.args.delete:
            print("\nTo perform this process automatically, add the --delete argument")
