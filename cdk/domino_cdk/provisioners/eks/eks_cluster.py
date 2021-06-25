from typing import Dict

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk.custom_resources as cr
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key


class DominoEksClusterProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope

    def provision(
        self,
        stack_name: str,
        eks_version: eks.KubernetesVersion,
        private_api: bool,
        secrets_encryption_key_arn: str,
        vpc: ec2.Vpc,
        bastion_sg: ec2.SecurityGroup,
        tags: Dict[str, str],
    ):
        eks_sg = ec2.SecurityGroup(
            self.scope,
            "EKSSG",
            vpc=vpc,
            security_group_name=f"{stack_name}-EKSSG",
            allow_all_outbound=False,
        )

        if secrets_encryption_key_arn:
            key = Key.from_key_arn(self.scope, "secrets_encryption_key_arn", secrets_encryption_key_arn)
        else:
            key = Key(
                self.scope,
                f"{stack_name}-kubernetes-secrets-envelope-key",
                alias=f"{stack_name}-kubernetes-secrets-envelope-key",
                removal_policy=cdk.RemovalPolicy.DESTROY,
                enable_key_rotation=True,
            )

        cluster = eks.Cluster(
            self.scope,
            "eks",
            cluster_name=stack_name,
            vpc=vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if private_api else None,
            vpc_subnets=[ec2.SubnetType.PRIVATE],
            version=eks_version,
            default_capacity=0,
            security_group=eks_sg,
            secrets_encryption_key=key,
        )

        params = {
            "name": cluster.cluster_name,
            "logging": {
                "clusterLogging": [
                    {
                        "enabled": True,
                        "types": ["api", "audit", "authenticator", "controllerManager", "scheduler"],
                    },
                ],
            },
        }

        cr.AwsCustomResource(
            self.scope,
            "UpdateClusterConfigCustom",
            timeout=cdk.Duration.minutes(10),  # defaults to 2 minutes
            log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_create={
                "service": "EKS",
                "action": "updateClusterConfig",
                "parameters": params,
                "physical_resource_id": cr.PhysicalResourceId.of("UpdateClusterConfigCustom"),
                # If the cluster already has logging enabled, this call will return error "already in desired state"
                # We ignore errors here. "..." is regexp for all 3-digit error codes because we cannot find what is the
                # actual error code. It is not 2.. 3.. 4.. 5..
                # We have a JIRA to explore this further: https://dominodatalab.atlassian.net/browse/PLAT-2439
                "ignore_error_codes_matching": "...",
            },
        )

        params = {
            "resourceArn": f"arn:aws:eks:{self.scope.region}:{self.scope.account}:cluster/{cluster.cluster_name}",
            "tags": tags,
        }

        cr.AwsCustomResource(
            self.scope,
            "TagClusterCustom",
            # timeout defaults to 2 minutes
            log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_create={
                "service": "EKS",
                "action": "tagResource",
                "parameters": params,
                "physical_resource_id": cr.PhysicalResourceId.of("TagClusterCustom"),
            },
        )

        if bastion_sg:
            cluster.cluster_security_group.add_ingress_rule(
                peer=bastion_sg,
                connection=ec2.Port(
                    protocol=ec2.Protocol("TCP"),
                    string_representation="API Access",
                    from_port=443,
                    to_port=443,
                ),
            )

        # account_id = cdk.Stack.of(self.scope).account
        # cluster.aws_auth.add_masters_role(
        #     iam.Role.from_role_arn(self.scope, "okta-fulladmin", f"arn:aws-us-gov:iam::{account_id}:role/okta-fulladmin")
        # )
        # cluster.aws_auth.add_masters_role(
        #     iam.Role.from_role_arn(self.scope, "okta-poweruser", f"arn:aws-us-gov:iam::{account_id}:role/okta-poweruser")
        # )

        return cluster
