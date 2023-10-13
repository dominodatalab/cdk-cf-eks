import re
from typing import Any, Dict, Optional

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
import boto3
from aws_cdk import CfnOutput, RemovalPolicy
from aws_cdk.aws_kms import Key
from aws_cdk.lambda_layer_kubectl_v24 import KubectlV24Layer
from aws_cdk.lambda_layer_kubectl_v25 import KubectlV25Layer
from aws_cdk.lambda_layer_kubectl_v26 import KubectlV26Layer
from aws_cdk.region_info import Fact, FactName
from constructs import Construct

from ..lambda_utils import create_lambda


class DominoEksClusterProvisioner:
    def __init__(
        self,
        scope: Construct,
    ) -> None:
        self.scope = scope
        self._addon_cache: Optional[Dict[str, Any]] = None

    def provision(
        self,
        stack_name: str,
        grandparent: Construct,
        eks_version: eks.KubernetesVersion,
        private_api: bool,
        service_ipv4_cidr: str,
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
                removal_policy=RemovalPolicy.DESTROY,
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

        if eks_version == "1.24":
            kubectl_layer = KubectlV24Layer(self.scope, "kubectl_layer")
        elif eks_version == "1.25":
            kubectl_layer = KubectlV25Layer(self.scope, "kubectl_layer")
        elif eks_version == "1.26":
            kubectl_layer = KubectlV26Layer(self.scope, "kubectl_layer")
        else:
            kubectl_layer = KubectlV26Layer(self.scope, "kubectl_layer")

        master_role = iam.Role(
            self.scope,
            "MastersRole",
            assumed_by=iam.AccountRootPrincipal(),
        )

        cluster = eks.Cluster(
            self.scope,
            "eks",
            cluster_name=stack_name,
            vpc=vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if private_api else None,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            masters_role=master_role,
            version=eks_version,
            kubectl_layer=kubectl_layer,
            default_capacity=0,
            security_group=eks_sg,
            secrets_encryption_key=key,
            service_ipv4_cidr=service_ipv4_cidr,
            prune=False,  # https://github.com/aws/aws-cdk/issues/19843
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

        self.setup_addons(cluster, eks_version.version)

        CfnOutput(
            grandparent,
            "eks_kubeconfig_cmd",
            value=f"aws eks update-kubeconfig --name {cluster.cluster_name} --region {self.scope.region} --role-arn {master_role.role_arn}",
        )
        return cluster

    def setup_addons(self, cluster: eks.Cluster, eks_version: str) -> eks.CfnAddon:
        def addon(addon: str) -> eks.CfnAddon:
            return eks.CfnAddon(
                self.scope,
                addon,
                addon_name=addon,
                cluster_name=cluster.cluster_name,
                resolve_conflicts="OVERWRITE",
                addon_version=self._get_addon_version(addon, eks_version),
            )

        vpc_cni_addon = addon("vpc-cni")
        addon("coredns")
        addon("kube-proxy")

        # Until https://github.com/aws/amazon-vpc-cni-k8s/issues/1291 is resolved
        patch = eks.KubernetesPatch(
            self.scope,
            "vpc-cni-selinux",
            cluster=cluster,
            resource_name="daemonset/aws-node",
            resource_namespace="kube-system",
            apply_patch={"spec": {"template": {"spec": {"securityContext": {"seLinuxOptions": {"type": "spc_t"}}}}}},
            restore_patch={},
        )

        patch.node.add_dependency(vpc_cni_addon)

    def _get_addon_version(self, addon: str, eks_version: str):
        if not self._addon_cache:
            eks_client = boto3.client("eks", self.scope.region)
            result = eks_client.describe_addon_versions(kubernetesVersion=eks_version)
            self._addon_cache = {a["addonName"]: a for a in result["addons"]}

        addon_versions = self._addon_cache[addon]["addonVersions"]

        if default_version := next(
            (
                version["addonVersion"]
                for version in addon_versions
                if any(c["defaultVersion"] for c in version["compatibilities"])
            ),
            None,
        ):
            return default_version

        versions = [v["addonVersion"] for v in addon_versions]
        return sorted(versions, key=lambda version: [int(part) for part in re.findall(r"([0-9]+)", version)])[-1]
