from typing import Dict, List

import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
from aws_cdk.aws_s3 import Bucket
from constructs import Construct

from domino_cdk import config
from domino_cdk.provisioners.eks.eks_cluster import DominoEksClusterProvisioner
from domino_cdk.provisioners.eks.eks_iam import DominoEksIamProvisioner
from domino_cdk.provisioners.eks.eks_nodegroup import DominoEksNodegroupProvisioner


class DominoEksProvisioner:
    def __init__(
        self,
        parent: Construct,
        construct_id: str,
        stack_name: str,
        eks_cfg: config.EKS,
        vpc: ec2.Vpc,
        private_subnet_name: str,
        bastion_sg: ec2.SecurityGroup,
        r53_zone_ids: List[str],
        nest: bool,
        buckets: Dict[str, Bucket],
        **kwargs,
    ) -> None:
        self.scope = cdk.NestedStack(parent, construct_id, **kwargs) if nest else parent

        self.scope.untagged_resources = parent.untagged_resources

        eks_version = eks.KubernetesVersion.of(eks_cfg.version)

        self.cluster = DominoEksClusterProvisioner(self.scope).provision(
            stack_name,
            eks_version,
            eks_cfg.private_api,
            eks_cfg.secrets_encryption_key_arn,
            vpc,
            bastion_sg,
            parent.cfg.tags,
        )
        ng_role = DominoEksIamProvisioner(self.scope).provision(
            stack_name, self.cluster.cluster_name, r53_zone_ids, buckets
        )
        DominoEksNodegroupProvisioner(
            self.scope, self.cluster, ng_role, stack_name, eks_cfg, eks_version, vpc, private_subnet_name, bastion_sg
        )

        cdk.CfnOutput(parent, "eks_cluster_name", value=self.cluster.cluster_name)

        region = cdk.Stack.of(self.scope).region
        cdk.CfnOutput(
            parent,
            "eks_kubeconfig_cmd",
            value=f"aws eks update-kubeconfig --name {self.cluster.cluster_name} --region {region} --role-arn {self.cluster.kubectl_role.role_arn}",
        )
