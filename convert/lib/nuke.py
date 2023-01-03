#!/usr/bin/env python3
import boto3
import re
from pprint import pprint

from .meta import cdk_ids


class nuke:
    def __init__(self, region: str, verbose: bool = False, delete: bool = False):
        self.region = region
        self.verbose = verbose
        self.delete = delete

    @property
    def autoscaling(self):
        if not getattr(self, "_autoscaling", None):
            self._autoscaling = boto3.client("autoscaling", self.region)
        return self._autoscaling

    @property
    def ec2(self):
        if not getattr(self, "_ec2", None):
            self._ec2 = boto3.client("ec2", self.region)
        return self._ec2

    @property
    def iam(self):
        if not getattr(self, "_iam", None):
            self._iam = boto3.client("iam", self.region)
        return self._iam

    @property
    def awslambda(self):
        if not getattr(self, "_lambda", None):
            self._awslambda = boto3.client("lambda", self.region)
        return self._awslambda

    @property
    def ssm(self):
        if not getattr(self, "_ssm", None):
            self._ssm = boto3.client("ssm", self.region)
        return self._ssm

    @property
    def stepfunctions(self):
        if not getattr(self, "_stepfunctions", None):
            self._stepfunctions = boto3.client("stepfunctions", self.region)
        return self._stepfunctions

    def _aws_list_all(self, list_func, parser, next_token_name: str = "Marker", next_token_arg: str = None, extra_args: dict = None):
        next_token_arg = next_token_arg or next_token_name
        all_things = []
        list_args = extra_args or {}
        while True:
            list_result = list_func(**list_args)
            all_things.extend(parser(list_result))
            if next_token := list_result.get(next_token_name):
                list_args = extra_args or {} | {next_token_arg: next_token}
            else:
                return all_things

    def _get_from_paged_list(self, things: list[str], list_func, parser, next_token_name: str = "Marker", next_token_arg: str = None, extra_args: dict = None):
        all_things = self._aws_list_all(list_func, parser, next_token_name, next_token_arg)

        existing_things = []
        for thing in things:
            if thing in all_things:
                existing_things.append(thing)
            elif self.verbose:
                print(f"{thing} doesn't exist")

        return existing_things

    def asg(self, group_names: list[str]):
        if not group_names:
            return
        existing_groups = self._get_from_paged_list(
            group_names,
            self.autoscaling.describe_auto_scaling_groups,
            lambda x: [i["AutoScalingGroupName"] for i in x["AutoScalingGroups"]],
            "NextToken",
        )

        if existing_groups:
            pprint({"Auto scaling groups to delete": existing_groups})

            if self.delete:
                for group in existing_groups:
                    print(
                        self.autoscaling.delete_auto_scaling_group(
                            AutoScalingGroupName=group
                        )
                    )

    def eip(self, eip_addresses: list[str]):
        if not eip_addresses:
            return
        result = self.ec2.describe_addresses()
        existing_allocations = [[i["AllocationId"], i.get("AssociationId")] for i in result["Addresses"] if i["PublicIp"] in eip_addresses]

        if existing_allocations:
            pprint({"Elastic IP allocation IDs to delete": existing_allocations})

            if self.delete:
                for allocation_id, association_id in existing_allocations:
                    if association_id:
                        print(self.ec2.disassociate_address(AssociationId=association_id))
                    print(self.ec2.release_address(AllocationId=allocation_id))

    def flowlog(self, flow_logs: list[str]):
        if not flow_logs:
            return
        result = self.ec2.describe_flow_logs(FlowLogIds=flow_logs)
        existing_flow_logs = [i["FlowLogId"] for i in result["FlowLogs"]]

        if existing_flow_logs:
            pprint({"Flow Log IDs to delete": existing_flow_logs})

            if self.delete:
                self.ec2.delete_flow_logs(FlowLogIds=existing_flow_logs)

    def instance(self, instance_ids: list[str]):
        if not instance_ids:
            return
        result = self.ec2.describe_instances(InstanceIds=instance_ids)
        if not result["Reservations"]:
            return
        existing_instances = [
            i["InstanceId"] for i in result["Reservations"][0]["Instances"] if i["State"]["Name"] != "terminated"
        ]

        if existing_instances:
            pprint({"Instance IDs to delete": existing_instances})

            if self.delete:
                self.ec2.terminate_instances(InstanceIds=existing_instances)

    def launch_template(self, launch_templates: list[str]):
        if not launch_templates:
            return
        existing_templates = self._get_from_paged_list(
            launch_templates,
            self.ec2.describe_launch_templates,
            lambda x: [i["LaunchTemplateId"] for i in x["LaunchTemplates"]],
            "NextToken",
        )

        if existing_templates:
            pprint({"Launch Template IDs to delete": existing_templates})

            if self.delete:
                for template_id in existing_templates:
                    self.ec2.delete_launch_template(LaunchTemplateId=template_id)

    def security_group(self, security_groups: list[str]):
        if not security_groups:
            return
        result = self.ec2.describe_security_groups()
        existing_sgs = [i["GroupId"] for i in result["SecurityGroups"] if i["GroupId"] in security_groups]

        if existing_sgs:
            pprint({"Security Group IDs to delete": existing_sgs})

            if self.delete:
                for sg in existing_sgs:
                    self.ec2.delete_security_group(GroupId=sg)

    def instance_profile(self, instance_profiles: list[str]):
        if not instance_profiles:
            return
        existing_profiles = self._get_from_paged_list(
            instance_profiles,
            self.iam.list_instance_profiles,
            lambda x: [p["InstanceProfileName"] for p in x["InstanceProfiles"]],
        )

        if existing_profiles:
            pprint({"Instance Profile IDs to delete": existing_profiles})

            if self.delete:
                for profile in existing_profiles:
                    self.iam.delete_instance_profile(InstanceProfileName=profile)

    def iam_policy(self, policies: list[str]):
        if not policies:
            return
        existing_policies = self._get_from_paged_list(
            policies,
            self.iam.list_policies,
            lambda x: [p["Arn"] for p in x["Policies"]],
        )

        if existing_policies:
            pprint({"IAM Policies to delete": existing_policies})

            if self.delete:
                for policy in existing_policies:
                    self.iam.delete_policy(PolicyArn=policy)

    def iam_role(self, roles: list[str]):
        if not roles:
            return
        existing_roles = self._get_from_paged_list(
            roles,
            self.iam.list_roles,
            lambda x: [r["RoleName"] for r in x["Roles"]],
        )

        if not existing_roles:
            return

        pprint({"IAM Roles to delete": existing_roles})

        if self.delete:
            for role in existing_roles:
                # jfc
                attached_policies = self._aws_list_all(
                    self.iam.list_attached_role_policies,
                    lambda x: [rp["PolicyArn"] for rp in x["AttachedPolicies"]],
                    extra_args={"RoleName": role},
                )
                for policy_arn in attached_policies:
                    self.iam.detach_role_policy(RoleName=role, PolicyArn=policy_arn)

                inline_policies = self._aws_list_all(
                    self.iam.list_role_policies,
                    lambda x: [ip for ip in x["PolicyNames"]],
                    extra_args={"RoleName": role},
                )
                for policy_name in inline_policies:
                    self.iam.delete_role_policy(RoleName=role, PolicyName=policy_name)

                instance_profiles = self._aws_list_all(
                    self.iam.list_instance_profiles_for_role,
                    lambda x: [ip["InstanceProfileName"] for ip in x["InstanceProfiles"]],
                    extra_args={"RoleName": role},
                )
                for ip_name in instance_profiles:
                    self.iam.remove_role_from_instance_profile(RoleName=role, InstanceProfileName=ip_name)
                self.iam.delete_role(RoleName=role)

    def stepfunctions_statemachine(self, statemachines: list[str]):
        if not statemachines:
            return
        existing_sms = self._get_from_paged_list(
            statemachines,
            self.stepfunctions.list_state_machines,
            lambda x: [sm["stateMachineArn"] for sm in x["stateMachines"]],
            "nextToken"
        )

        if existing_sms:
            pprint({"Stepfunctions Statemachines to delete": existing_sms})

            if self.delete:
                for sm in existing_sms:
                    self.stepfunctions.delete_state_machine(stateMachineArn=sm)

    def lambda_function(self, funcs: list[str]):
        if not funcs:
            return
        existing_funcs = self._get_from_paged_list(
            funcs,
            self.awslambda.list_functions,
            lambda x: [f["FunctionName"] for f in x["Functions"]],
            "NextMarker",
            next_token_arg="Marker",
        )

        if existing_funcs:
            pprint({"Lambda Functions to delete": existing_funcs})

            if self.delete:
                for func in existing_funcs:
                    self.awslambda.delete_function(FunctionName=func)

    def lambda_layerversion(self, layerversions: list[str]):
        if not layerversions:
            return
        layerversion_results = {}
        for layerversion_arn in layerversions:
            if re_result := re.match("arn:aws(?:-us-gov)?:lambda:[\w\-]+:\d+:layer:(\w*):(\d+)", layerversion_arn):
                layer, version = re_result.groups(1)
                version = int(version)
                try:
                    layer_result = self.awslambda.get_layer_version(LayerName=layer, VersionNumber=version)
                    if layer_result["LayerVersionArn"] == layerversion_arn:
                        layerversion_results[layerversion_arn] = {"LayerName": layer, "VersionNumber": version}
                except:
                    pass

        if layerversion_results:
            pprint({"Lambda Layer Versions to delete": layerversion_results})

            if self.delete:
                for lv in layerversion_results.values():
                    self.awslambda.delete_layer_version(**lv)


    def ssm_parameter(self, parameters: list[str]):
        if not parameters:
            return
        existing_parameters = self._get_from_paged_list(
            parameters,
            self.ssm.describe_parameters,
            lambda x: [p["Name"] for p in x["Parameters"]],
            "NextToken",
        )

        if existing_parameters:
            pprint({"SSM Parameters to delete": existing_parameters})

            if self.delete:
                for p in existing_parameters:
                    self.ssm.delete_parameter(Name=p)

    def nuke(self, nuke_queue: dict[str, list[str]], remove_security_group_references: bool = False):
        all_referenced_groups = {}
        if security_groups := nuke_queue.get(cdk_ids.security_group.value):
            for sg in security_groups:
                if referenced_groups := [r for r in self.ec2.describe_security_group_rules()["SecurityGroupRules"] if r.get("ReferencedGroupInfo", {}).get("GroupId") == sg]:
                    if not remove_security_group_references or not self.delete:
                        all_referenced_groups[f"{sg} is referenced by"] = set(r["GroupId"] for r in referenced_groups)
                    else:
                        for rule in referenced_groups:
                            if rule["IsEgress"]:
                                self.ec2.revoke_security_group_egress(GroupId=rule["GroupId"], SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]])
                            else:
                                self.ec2.revoke_security_group_ingress(GroupId=rule["GroupId"], SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]])

        if all_referenced_groups:
            pprint({"Security groups to be deleted": security_groups})
            print("\nHowever, some security groups have rules referencing them that must be removed:\n")
            pprint(all_referenced_groups)

            if self.delete:
                print("\nRemove all references before running this command, or re-run with --remove-security-group-references.")
                exit(1)

        local_queue = []
        order = [cdk_ids.asg, cdk_ids.instance, cdk_ids.eip, cdk_ids.flowlog, cdk_ids.launch_template, cdk_ids.security_group, cdk_ids.stepfunctions_statemachine, cdk_ids.lambda_function, cdk_ids.lambda_layerversion, cdk_ids.iam_role, cdk_ids.iam_policy, cdk_ids.instance_profile, cdk_ids.ssm_parameter]
        for x in order:
            if x.value in nuke_queue:
                resource_list = nuke_queue.pop(x.value)
                local_queue.append([getattr(self, x.name), resource_list])
        if nuke_queue:
            pprint({"Don't know how to process": nuke_queue})
            print("Note: this is an ERROR")
            exit(1)
        for func, resource_list in local_queue:
            func(resource_list)
        print("\nNote: You may still have lambda-associated network interfaces. They should be deleted automatically within 24 hours.")

        if all_referenced_groups:
            print("\nSee security group note at top of output!")
