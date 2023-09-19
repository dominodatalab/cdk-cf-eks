#!/usr/bin/env python3

import argparse
import json
import re
import shlex
import shutil
from copy import deepcopy
from functools import cached_property
from os import listdir, makedirs
from os.path import abspath, exists, join
from pathlib import Path
from pprint import pprint
from subprocess import check_output, run
from sys import stderr
from textwrap import dedent
from time import sleep
from typing import Any

import boto3
import yaml
from packaging import version

from .meta import cdk_ids, cf_status, stack_map
from .nuke import nuke

resources = {}

for filename in listdir("data"):
    with open(join("data", filename)) as f:
        r = yaml.safe_load(f.read())
    resources[r.pop("name")] = r

clean_categories = [x.name for x in cdk_ids if x.name != "cloudformation_stack"]


def nested_az_replace(d: dict, count: int):
    for k, v in d.items():
        if isinstance(v, str):
            d[k] = re.sub("%az_count%", str(count), d[k])
            d[k] = re.sub("%az_count_plus%", str(count + 1), d[k])
        elif isinstance(v, list):
            for i, entry in enumerate(v):
                if isinstance(entry, dict):
                    v[i] = nested_az_replace(entry, count)
                else:
                    raise Exception(f"Unexpected resource map entry {k}: {v}")
        elif isinstance(v, dict):
            d[k] = nested_az_replace(v, count)
        else:
            raise Exception(f"Unexpected resource map entry {k}: {v}")
    return d


def check_binary(binary_name: str, version_args: str, version_regex=None, min_version=None):
    try:
        cmd = f"{binary_name} {version_args}"
        print(f"Running: `{cmd}`")
        out = check_output(shlex.split(cmd)).decode("utf-8")

        v_re = r"\d+(\.\d+)*" if not version_regex else version_regex
        if re_match := re.search(v_re, out):
            installed_version = re_match.group(0)
            print(f"{binary_name} is installed, version: {installed_version}\n")

            if min_version:
                installed_version_parsed = version.parse(installed_version)
                minimum_version = version.parse(min_version)
                if installed_version_parsed < minimum_version:
                    print(
                        f"FAIL: The installed version of {binary_name} is less than the minimum required version ({min_version})\n"
                    )
                    return 1
        else:
            print("{v_re} failed to match any versions")
            return 1

        return 0

    except Exception as e:
        print(f"An error occurred: {e}")
        return 1


class app:
    def __init__(self):
        self.parse_args()
        self.args.command()
        self.setup_boto_clients()

    @cached_property
    def config(self) -> dict[str, Any]:
        config_file = Path("config.yaml")
        if not exists(config_file):
            raise Exception(f"{config_file} does not exist.")
        with open(config_file, "r") as f:
            return yaml.safe_load(f.read())

    @cached_property
    def requirements(self) -> dict[str, Any]:
        r_file = Path("requirements.yaml")
        if not exists(r_file):
            raise Exception(f"{r_file} does not exist.")
        with open(r_file, "r") as f:
            return yaml.safe_load(f.read())

    @property
    def region(self) -> str:
        return self.config["AWS_REGION"]

    @property
    def stack_name(self) -> str:
        return self.config["STACK_NAME"]

    @property
    def mod_version(self) -> str:
        return self.config["MOD_VERSION"]

    def get_stacks(self, stack: str = None, full: bool = False):
        stacks = {"resources": {}}
        p = self.cf.get_paginator("list_stack_resources")
        resources = [
            summary for i in p.paginate(StackName=stack or self.stack_name) for summary in i["StackResourceSummaries"]
        ]
        for r in resources:
            logical_id = r["LogicalResourceId"]
            physical_id = r["PhysicalResourceId"]
            if r["ResourceType"] == cdk_ids.eip.value:
                # Extracting EIP AllocationId from ec2 as its not avaiable from cf
                response = self.ec2.describe_addresses(PublicIps=[physical_id])
                if eip_allocation_id := response["Addresses"][0]["AllocationId"]:
                    physical_id = eip_allocation_id
            if r["ResourceType"] == cdk_ids.cloudformation_stack.value:
                for mapped_logical_id, name in stack_map.items():
                    if logical_id.startswith(mapped_logical_id):
                        try:
                            stacks[name] = self.get_stacks(physical_id, full)
                        except self.cf.exceptions.ClientError as e:
                            if "does not exist" in e.response["Error"]["Message"]:
                                stacks[name] = None
                            else:
                                raise
                        break
                else:
                    raise Exception(f"Nothing to map stack {r} to!")
            else:
                parsed_logical_id = logical_id[:-8] if re.match("^[0-9A-F]{8}", logical_id[-8:]) else logical_id
                stacks["resources"][parsed_logical_id] = r if full else physical_id
        return stacks

    def setup_boto_clients(self):
        self.cf = boto3.client("cloudformation", self.region)
        self.ec2 = boto3.client("ec2", self.region)
        self.eks = boto3.client("eks", self.region)
        self.iam = boto3.client("iam", self.region)
        self.r53 = boto3.client("route53", self.region)

    def setup(self, full: bool = False, no_stacks: bool = False):
        self.cf_stack_key = re.sub(r"\W", "", self.stack_name)

        self.setup_boto_clients()

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

        setup_tf_mods_parser = subparsers.add_parser(
            name="setup-tf-modules", help="Sets up the terraform module", parents=[common_parser]
        )
        setup_tf_mods_parser.set_defaults(command=self.setup_tf_mods)

        check_requirements = subparsers.add_parser(
            name="check-requirements", help="Checks if requirements are installed", parents=[common_parser]
        )
        check_requirements.set_defaults(command=self.check_requirements)

        create_tfvars_parser = subparsers.add_parser(
            name="create-tfvars", help="Generate tfvars", parents=[common_parser]
        )
        create_tfvars_parser.add_argument("--ssh-key-path", help="Path to local SSH key to cluster", required=True)
        create_tfvars_parser.set_defaults(command=self.create_tfvars)

        resource_map_parser = subparsers.add_parser(
            name="resource-map",
            help="Create resource map for customization/debugging of set-imports command (optional step)",
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
            "--unmanaged-nodegroups",
            help="Whether or not unmanaged nodegroups are in use",
            default=False,
            action="store_true",
        )
        resource_map_parser.add_argument(
            "--flow-logging", help="Whether or not flow logging is configured", default=False, action="store_true"
        )
        resource_map_parser.add_argument(
            "--efs-backups",
            help="Whether or not to import efs backup vault",
            default=True,
            action=argparse.BooleanOptionalAction,
        )
        resource_map_parser.set_defaults(command=self.resource_map)

        import_parser = subparsers.add_parser(
            name="set-imports",
            help="Writes import blocks to the corresponding terraform module",
            parents=[common_parser],
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
        import_parser.set_defaults(command=self.write_imports)

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

    def check_requirements(self):
        binaries = self.requirements["binaries"]
        return_codes = []
        for b, args in binaries.items():
            return_codes.append(
                check_binary(
                    binary_name=b,
                    version_args=args.get("version_args"),
                    min_version=args.get("min_version"),
                    version_regex=args.get("version_regex"),
                )
            )

        if any(code != 0 for code in return_codes):
            raise Exception("One or more binaries failed the check.")

    def print_stack(self):
        self.setup(full=self.args.verbose)
        out = self.stacks[self.args.sub_stack] if self.args.sub_stack else self.stacks
        if self.args.yaml:
            print(yaml.safe_dump(out))
        else:
            pprint(out)

    def generate_resource_map(
        self,
        availability_zones: int,
        efs_backups: bool,
        route53: bool,
        bastion: bool,
        monitoring: bool,
        unmanaged_nodegroups: bool,
        flow_logging: bool,
    ) -> dict:
        template = resources["resource_template"]["resources"]

        optional_resources = []
        for count in range(availability_zones):
            az_template = nested_az_replace(deepcopy(resources["per_az"]), count)
            optional_resources.append(az_template)

        if efs_backups:
            optional_resources.append(resources["efs_backup"])
        if route53:
            optional_resources.append(resources["route53"])
        if flow_logging:
            optional_resources.append(resources["flow_logging"])
        if monitoring:
            optional_resources.append(resources["monitoring_bucket"])
        if bastion:
            optional_resources.append(resources["bastion"])
        if unmanaged_nodegroups:
            optional_resources.append(resources["unmanaged_nodegroup"])

        for resource in optional_resources:
            for key in resource["resources"].keys():
                template[key].extend(resource["resources"][key])

        return template

    def resource_map(self):
        resource_map = self.generate_resource_map(
            self.args.availability_zones,
            self.args.efs_backups,
            self.args.route53,
            self.args.bastion,
            self.args.monitoring,
            self.args.unmanaged_nodegroups,
            self.args.flow_logging,
        )
        print(yaml.safe_dump(resource_map))

    def t(self, val: str) -> str:
        val = re.sub(r"%stack_name%", self.stack_name, val)
        val = re.sub(r"%cf_stack_key%", self.cf_stack_key, val)
        return val

    def get_imports(self, resource_map: dict):
        import_template = dedent(
            """
                import {{
                    id = "{resource_id}"
                    to = {tf_import_path}
                  }}
                """
        )

        imports: dict[str, list[str]] = {"cdk_tf": [], "infra": [], "cluster": [], "nodes": []}

        for map_stack, items in resource_map.items():
            resources = self.stacks[map_stack]["resources"]
            for item in items:
                tf_import_path = self.t(item["tf"])
                if value := item.get("value"):
                    resource_id = self.t(value)
                elif cf_sgr := item.get("cf_sgr"):
                    sg = resources[self.t(cf_sgr["sg"])]
                    append_rule_sg = ""
                    if rule_sg := cf_sgr.get("rule_sg"):
                        rule_sg_r = resources
                        if rule_sg_stack := cf_sgr.get("rule_sg_stack"):
                            rule_sg_r = self.stacks[self.t(rule_sg_stack)]["resources"]
                        append_rule_sg = rule_sg_r[self.t(rule_sg)]
                    resource_id = f"{sg}{self.t(cf_sgr['rule'])}{append_rule_sg}"
                elif cf_igw_attachment := item.get("cf_igw_attachment"):
                    igw_id = resources[self.t(cf_igw_attachment["igw"])]
                    vpc_id = resources[self.t(cf_igw_attachment["vpc"])]
                    resource_id = f"{igw_id}:{vpc_id}"
                elif assoc := item.get("cf_rtassoc"):
                    resource_id = f"{resources[self.t(assoc['subnet'])]}/{resources[self.t(assoc['route_table'])]}"
                elif bkpsel := item.get("cf_backupselection"):
                    selection_id, plan_id = resources[self.t(bkpsel)].split("_")
                    resource_id = f"{plan_id}|{selection_id}"
                else:
                    resource_id = resources[self.t(item["cf"])]

                import_block = import_template.format(tf_import_path=tf_import_path, resource_id=resource_id)

                if tf_import_path.startswith("module.infra"):
                    imports["infra"].append(import_block)
                elif tf_import_path.startswith("module.eks"):
                    imports["cluster"].append(import_block)
                elif tf_import_path.startswith("module.nodes"):
                    imports["nodes"].append(import_block)
                else:
                    imports["cdk_tf"].append(import_block)

        eks_cluster_result = self.eks.describe_cluster(name=self.cdkconfig["name"])
        eks_cluster_auto_sg = eks_cluster_result["cluster"]["resourcesVpcConfig"]["clusterSecurityGroupId"]
        imports["cdk_tf"].append(
            import_template.format(
                tf_import_path="aws_security_group.eks_cluster_auto", resource_id=eks_cluster_auto_sg
            )
        )

        return imports

    def write_imports(self):
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
                unmanaged_nodegroups=self.cdkconfig["eks"]["unmanaged_nodegroups"],
                flow_logging=self.cdkconfig["vpc"]["flow_logging"],
            )

        imports = self.get_imports(resource_map)
        for component, import_values in imports.items():
            self.write_blocks(component, import_values)

    def write_blocks(self, component: str, imports: list) -> None:
        deploy_dir = self.stack_name
        terraform_dir = Path(deploy_dir, "terraform")
        imports_path = Path(terraform_dir, component, "imports.tf")
        with open(imports_path, "w") as f:
            f.writelines(i for i in imports)

    def tf_sh(self, component: str, command: str) -> None:
        deploy_dir = self.stack_name
        cmd = [
            "./tf.sh",
            component,
            command,
        ]
        print(f"Running {cmd}...")
        tf_sh_run = run(cmd, cwd=deploy_dir, capture_output=True, text=True)
        if tf_sh_run.returncode != 0:
            print(f"Error Running from module {cmd} failed.", tf_sh_run.stdout, tf_sh_run.stderr)
            exit(1)

    def setup_tf_mods(self):
        self.setup()
        print("Setting up terraform modules...")

        deploy_dir = self.stack_name
        mod_version = self.mod_version
        example_url = f"github.com/dominodatalab/terraform-aws-eks.git//examples/deploy?ref={mod_version}"

        makedirs(deploy_dir, exist_ok=True)
        cmd = [
            "terraform",
            f"-chdir={deploy_dir}",
            "init",
            "-backend=false",
            f"-from-module={example_url}",
        ]
        print(f"Running {cmd}...")
        tf_mod_run = run(cmd, capture_output=True, text=True)
        if tf_mod_run.returncode != 0:
            print("Error Initializing from module command failed.", tf_mod_run.stdout, tf_mod_run.stderr)
            exit(1)

        mod_version_sh = join(self.stack_name, "set-mod-version.sh")

        mod_version_run = run(["bash", mod_version_sh, mod_version], capture_output=True, text=True)

        if mod_version_run.returncode != 0:
            print("Error setting module version.", mod_version_run.stdout, mod_version_run.stderr)
            exit(1)

        shutil.copytree(Path("cdk_tf"), Path(deploy_dir, "terraform", "cdk_tf"))

        for mod in ["cdk_tf", "all"]:
            self.tf_sh(mod, "init")

    def create_tfvars(self):
        self.setup()

        def get_subnet_ids(subnet_type: str, prefix: str = "VPC"):
            return [
                v
                for k, v in self.stacks["vpc_stack"]["resources"].items()
                if re.match(f"{prefix}{self.cf_stack_key}{subnet_type}Subnet\\d+Subnet", k)
            ]

        ng_role_name = self.stacks["eks_stack"]["resources"][f"{self.cf_stack_key}NG"]
        ng_role_arn = self.iam.get_role(RoleName=ng_role_name)["Role"]["Arn"]
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
        # CDK force destroy is individually configurable
        # If any of them at all are not set to force destroy, turn the feature off
        s3_force_destroy = not [
            b for b in self.cdkconfig["s3"]["buckets"].values() if b and not b["auto_delete_objects"]
        ]

        eks_cluster_result = self.eks.describe_cluster(name=self.cdkconfig["name"])
        eks_k8s_version = eks_cluster_result["cluster"]["version"]
        eks_cluster_auto_sg = eks_cluster_result["cluster"]["resourcesVpcConfig"]["clusterSecurityGroupId"]

        route53_hosted_zone_name = None
        if r53_zone_ids := self.cdkconfig["route53"]["zone_ids"]:
            route53_hosted_zone_name = self.r53.get_hosted_zone(Id=r53_zone_ids[0])["HostedZone"]["Name"]

        subnet_result = self.ec2.describe_subnets(SubnetIds=get_subnet_ids("Private"))
        az_zone_ids = [s["AvailabilityZoneId"] for s in subnet_result["Subnets"]]

        tfvars: dict[str, dict[str, Any]] = {"cdk_tf": {}, "infra": {}, "cluster": {}, "nodes": {}}

        region = self.cdkconfig["aws_region"]
        deploy_id = self.cdkconfig["name"]
        tags = {**self.cdkconfig["tags"], "domino-deploy-id": self.cdkconfig["name"]}

        tfvars["cdk_tf"] = {
            "deploy_id": deploy_id,
            "region": region,
            "flow_logging": self.cdkconfig["vpc"]["flow_logging"],
            "eks_cluster_auto_sg": eks_cluster_auto_sg,
            "number_of_azs": self.cdkconfig["vpc"]["max_azs"],
            "tags": tags,
        }

        eks = {
            "k8s_version": eks_k8s_version,
            "public_access": {
                "enabled": eks_cluster_result["cluster"]["resourcesVpcConfig"]["endpointPublicAccess"],
                "cidrs": eks_cluster_result["cluster"]["resourcesVpcConfig"]["publicAccessCidrs"],
            },
            "custom_role_maps": eks_custom_role_maps,
        }

        if eks_creation_role_name := self.stacks["eks_stack"]["resources"]["eksCreationRole"]:
            eks["creation_role_name"] = eks_creation_role_name

        default_node_groups = {
            "platform": {
                "availability_zone_ids": az_zone_ids,
            },
            "compute": {
                "availability_zone_ids": az_zone_ids,
            },
            "gpu": {
                "availability_zone_ids": az_zone_ids,
            },
        }

        tfvars["infra"] = {
            "deploy_id": deploy_id,
            "region": region,
            "ssh_pvt_key_path": abspath(self.args.ssh_key_path),
            "network": {
                "vpc": {
                    "id": self.cdkconfig["vpc"]["id"]
                    if not self.cdkconfig["vpc"]["create"]
                    else self.stacks["vpc_stack"]["resources"]["VPC"],
                    "subnets": {
                        "private": get_subnet_ids("Private"),
                        "public": get_subnet_ids("Public"),
                        "pod": get_subnet_ids("Pod", ""),
                    },
                }
            },
            "tags": tags,
            "storage": {
                "s3": {"force_destroy_on_deletion": s3_force_destroy},
                "efs": {
                    "backup_vault": {
                        "create": self.cdkconfig["efs"]["backup"]["enable"],
                        "force_destroy": self.cdkconfig["efs"]["backup"]["removal_policy"] == "DESTROY",
                        "backup": {
                            "schedule": self.cdkconfig["efs"]["backup"]["schedule"],
                            "cold_storage_after": self.cdkconfig["efs"]["backup"]["move_to_cold_storage_after"],
                            "delete_after": self.cdkconfig["efs"]["backup"]["delete_after"],
                        },
                    }
                },
            },
            "kms": {
                "enabled": False,
            },
            "route53_hosted_zone_name": route53_hosted_zone_name,
            "bastion": {
                "enabled": eks_cluster_result["cluster"]["resourcesVpcConfig"]["endpointPrivateAccess"],
            },
            "eks": eks,  # Needs the k8s version.
            "default_node_groups": default_node_groups,  # Needs the nodes' flavors to compute/verify zones.
        }

        tfvars["cluster"]["eks"] = eks

        if eks_cluster_kms_key_arn := eks_cluster_result["cluster"]["encryptionConfig"][0]["provider"]["keyArn"]:
            tfvars["cluster"]["kms_info"] = {
                "enabled": True,
                "key_arn": eks_cluster_kms_key_arn,
                "key_id": eks_cluster_kms_key_arn.split(":")[-1].split("/")[1],
            }

        tfvars["nodes"] = {"default_node_groups": default_node_groups}

        mods_vars_dir = Path(self.cdkconfig["name"], "terraform")

        for mod, values in tfvars.items():
            tfvars_path = Path(mods_vars_dir, f"{mod}.tfvars")
            tfvars_path.unlink(missing_ok=True)
            self.write_json_tfvars(values, Path(f"{tfvars_path}.json"))

        notes = ""
        if len(r53_zone_ids) > 1:
            notes += f"\n* You have multiple hosted zones, only the first ({r53_zone_ids[0]} [{route53_hosted_zone_name}]) will be used."

        notes += (
            "\n* Nodegroup settings do not carry over. Please examine tfvars if you want to make any customizations."
        )

        if notes:
            print(f"*** IMPORTANT ***: {notes}", file=stderr)

    def write_json_tfvars(self, config: dict, filename: Path) -> None:
        with open(filename, "w") as f:
            f.write(json.dumps(config, indent=4))

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
                "eksNodegroup": [cdk_ids.eks_nodegroup.value],
            },
            "s3_stack": {
                "CustomS3AutoDeleteObjectsCustomResourceProvider": lambda_safe,
            },
            "vpc_stack": {
                "endpointssg": [cdk_ids.security_group.value],
                "(.*ENDPOINT|VPCS3)": [cdk_ids.endpoint.value],
                "bastion": [
                    cdk_ids.instance.value,
                    cdk_ids.instance_profile.value,
                    cdk_ids.iam_role.value,
                    cdk_ids.eip.value,
                ],
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

        empty_sg_rules = {"egress": [], "ingress": []}
        try:
            eks_cluster_sg = {
                self.eks.describe_cluster(name=self.stack_name)["cluster"]["resourcesVpcConfig"][
                    "clusterSecurityGroupId"
                ]: empty_sg_rules
            }
        except self.eks.exceptions.ResourceNotFoundException:
            eks_cluster_sg = {}

        unmanaged_sg = self.stacks["eks_stack"]["resources"].get("UnmanagedSG")

        eks_sg = self.stacks["eks_stack"]["resources"]["EKSSG"]["PhysicalResourceId"]

        rule_ids_to_nuke = {
            **eks_cluster_sg,
            eks_sg: {"egress": [], "ingress": []},
        }
        if unmanaged_sg:
            rule_ids_to_nuke[unmanaged_sg["PhysicalResourceId"]] = {"egress": [], "ingress": []}

        for group in rule_ids_to_nuke.keys():
            rules = [
                r
                for r in self.ec2.describe_security_group_rules(Filters=[{"Name": "group-id", "Values": [group]}])[
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

    def _print_stacks_status(self, stacks_names: list):
        for stack_name in stacks_names:
            stack_status = self.cf.describe_stacks(StackName=stack_name)["Stacks"][0]["StackStatus"]
            print("Stack:", stack_name, "Status:", stack_status)

    def _delete_stack_wait_for_fail_state(self, stack_name: str, role_arn: str):
        stack_details = self.cf.describe_stacks(StackName=stack_name)
        stack_status = stack_details["Stacks"][0]["StackStatus"]

        if stack_status != "DELETE_FAILED":
            print(f"Deleting Stack: {stack_name} Status: {stack_status}")
            self.cf.delete_stack(StackName=stack_name, RoleARN=role_arn)

        while (stack_status := self.cf.describe_stacks(StackName=stack_name)["Stacks"][0]["StackStatus"]) not in [
            "DELETE_FAILED",
            "DELETE_COMPLETED",
        ]:
            print(
                f"Waiting for stack{stack_name} to be in `DELETE_FAILED` or `DELETE_COMPLETED`...Currently: {stack_status}"
            )
            sleep(5)

        nested_stacks = self._get_nested_stacks(stack_name)

        self._print_stacks_status(nested_stacks)

        for nested_stack in nested_stacks:
            self._delete_stack_wait_for_fail_state(nested_stack, role_arn)

    def _get_nested_stacks(self, stack_name: str) -> list:
        stack_resources = self.cf.list_stack_resources(StackName=stack_name)

        nested_stacks = []
        for resource in stack_resources["StackResourceSummaries"]:
            if resource["ResourceType"] == cdk_ids.cloudformation_stack.value:
                nested_stacks.append(resource.get("PhysicalResourceId"))

        return nested_stacks

    def _get_stack_resources(self, stacks, s):
        child_id = s["PhysicalResourceId"]
        child_name = re.search(r":stack/(.*)/", child_id).group(1)
        try:
            if self.cf.describe_stacks(StackName=child_id)["Stacks"][0]["StackStatus"] == "DELETE_COMPLETE":
                return
        except self.cf.exceptions.ClientError as e:
            if "does not exist" in e.response["Error"]["Message"]:
                return
            raise

        child_resources = self.cf.describe_stack_resources(StackName=child_name)["StackResources"]
        stacks[child_name] = [
            r["LogicalResourceId"] for r in child_resources if r["ResourceStatus"] != "DELETE_COMPLETE"
        ]
        for r in child_resources:
            if r["ResourceType"] == cdk_ids.cloudformation_stack.value:
                self._get_stack_resources(stacks, r)

    def delete_stack(self):
        self.setup()

        cf_only_state_file = Path("cloudformation-only", "terraform.tfstate")

        if not exists(cf_only_state_file):
            print(f"Error: {cf_only_state_file} does not exist.")

        with open(cf_only_state_file, "r") as f:
            tfstate_data = json.load(f)

        cf_only_role = tfstate_data.get("outputs", {}).get("cloudformation_only_role", {}).get("value", None)

        if not cf_only_role or not re.match("arn:.*:iam:.*role/cloudformation-only", cf_only_role):
            print("Please run the terraform module in the 'cloudformation-only' subdirectory...")
            exit(1)

        if self.args.delete:
            print(f"Forcing {self.stack_name} into `DELETE_FAILED`")
            self._print_stacks_status([self.stack_name])
            self._delete_stack_wait_for_fail_state(self.stack_name, cf_only_role)

        root_resources = self.cf.describe_stack_resources(StackName=self.stack_name)["StackResources"]

        stacks = {
            self.stack_name: [
                r["LogicalResourceId"] for r in root_resources if r["ResourceStatus"] != "DELETE_COMPLETE"
            ]
        }

        for s in root_resources:
            if s["ResourceType"] == cdk_ids.cloudformation_stack.value:
                self._get_stack_resources(stacks, s)

        for i, (stack, resources) in enumerate(stacks.items()):
            if self.args.delete:
                print("Deleting stack:", stack)
                if (
                    stack_status := self.cf.describe_stacks(StackName=stack)["Stacks"][0]["StackStatus"]
                ) and stack_status != "DELETE_FAILED":
                    raise Exception(f"Expected stack status to be `DELETE_FAILED` but got: `{stack_status}`.")

                self.cf.delete_stack(StackName=stack, RoleARN=cf_only_role, RetainResources=resources)
            else:
                if i == 0:
                    print(
                        "Manual instructions:\nFirst run this delete-stack command using the cloudformation-only role:\n"
                    )
                    print(
                        f"aws cloudformation delete-stack --region {self.region} --stack-name {stack} --role {cf_only_role}\n"
                    )
                    print(
                        "This will *attempt* to delete the entire CDK stack, but *intentionally fail* so as to leave the stack in the delete failed state, with all resources having failed. This opens the gate to retain every resource, so the following runs can delete the stack(s) and only the stack(s). After running the first command, rerun this and then execute the following to safely delete the stacks:\n"
                    )
                print(
                    f"aws cloudformation delete-stack --region {self.region} --stack-name {stack} --retain-resources {' '.join(resources)} --role {cf_only_role}\n"
                )

        if not self.args.delete:
            print("\nTo perform this process automatically, add the --delete argument")
