from typing import Dict

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import boto3
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key
from aws_cdk.region_info import Fact, FactName

from ..lambda_utils import create_lambda


class DominoEksClusterProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope
        self._addon_cache = None

    def provision(
        self,
        stack_name: str,
        eks_version: eks.KubernetesVersion,
        private_api: bool,
        secrets_encryption_key_arn: str,
        vpc: ec2.Vpc,
        bastion_sg: ec2.SecurityGroup,
        tags: Dict[str, str],
    ) -> eks.Cluster:
        partition = Fact.require_fact(self.scope.region, FactName.PARTITION)

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

        log_cleanup_lambda_resource = create_lambda(
            scope=self.scope,
            stack_name=stack_name,
            name="cluster_post_deletion_tasks",
            properties={
                "cluster_name": stack_name,
            },
            resources=[
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:/aws/lambda/{stack_name}*",
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:*:log-stream:*",
            ],
            actions=[
                "logs:DescribeLogGroups",
                "logs:PutRetentionPolicy",
            ],
        )

        cluster = eks.Cluster(
            self.scope,
            "eks",
            cluster_name=stack_name,
            vpc=vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if private_api else None,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE)],
            version=eks_version,
            default_capacity=0,
            security_group=eks_sg,
            secrets_encryption_key=key,
        )

        # To make sure log cleanup is called after cluster cleanup: cluster depends on custom so custom is guaranteed
        # to be created before the cluster and deleted after the cluster
        cluster.node.add_dependency(log_cleanup_lambda_resource)

        create_lambda(
            scope=self.scope,
            stack_name=stack_name,
            name="cluster_post_creation_tasks",
            resources=[
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:/aws/eks/{cluster.cluster_name}/cluster",
                cluster.cluster_arn + "*",
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:*:log-stream:*",
            ],
            actions=[
                "logs:DescribeLogGroups",
                "logs:PutRetentionPolicy",
                "eks:TagResource",
                "eks:UpdateClusterConfig",
            ],
            properties={"cluster_name": cluster.cluster_name, "cluster_arn": cluster.cluster_arn, "tags": tags},
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

        eks.CfnAddon(
            self.scope,
            "kube-proxy",
            addon_name="kube-proxy",
            cluster_name=cluster.cluster_name,
            resolve_conflicts="OVERWRITE",
            addon_version=self.addon_version("kube-proxy", eks_version),
        )
        eks.CfnAddon(
            self.scope,
            "vpc-cni",
            addon_name="vpc-cni",
            cluster_name=cluster.cluster_name,
            resolve_conflicts="OVERWRITE",
            addon_version=self.addon_version("vpc-cni", eks_version),
        )
        eks.CfnAddon(
            self.scope,
            "coredns",
            addon_name="coredns",
            cluster_name=cluster.cluster_name,
            resolve_conflicts="OVERWRITE",
            addon_version=self.addon_version("coredns", eks_version),
        )

        return cluster

    def addon_version(self, addon: str, eks_version: str):
        if not self._addon_cache:
            eks = boto3.client("eks", self.scope.region)
            result = eks.describe_addon_versions()
            self._addon_cache = {a["addonName"]: a for a in result["addons"]}

        versions = [
            v["addonVersion"]
            for v in self._addon_cache[addon]["addonVersions"]
            if eks_version.version in [c["clusterVersion"] for c in v["compatibilities"]]
        ]

        return sorted(versions)[-1]
