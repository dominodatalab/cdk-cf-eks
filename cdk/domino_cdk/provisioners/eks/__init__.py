from typing import List

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk

from domino_cdk import config
from domino_cdk.provisioners.eks.eks_cluster import DominoEksClusterProvisioner
from domino_cdk.provisioners.eks.eks_iam import DominoEksIamProvisioner
from domino_cdk.provisioners.eks.eks_nodegroup import DominoEksNodegroupProvisioner


class DominoEksProvisioner:
    def __init__(
        self,
        parent: cdk.Construct,
        construct_id: str,
        name: str,
        eks_cfg: config.EKS,
        vpc: ec2.Vpc,
        private_subnet_name: str,
        bastion_sg: ec2.SecurityGroup,
        r53_zone_ids: List[str],
        s3_policy: iam.ManagedPolicy,
        nest: bool,
        **kwargs,
    ) -> None:
        self.scope = cdk.NestedStack(parent, construct_id, **kwargs) if nest else parent

        eks_version = getattr(eks.KubernetesVersion, f"V{eks_cfg.version.replace('.', '_')}")

        self.cluster = DominoEksClusterProvisioner(self.scope).provision(
            name, eks_version, eks_cfg.private_api, eks_cfg.secrets_encryption_key_arn, vpc, bastion_sg
        )
        ng_role = DominoEksIamProvisioner(self.scope).provision(
            name, self.cluster.cluster_name, s3_policy, r53_zone_ids
        )
        DominoEksNodegroupProvisioner(
            self.scope, self.cluster, ng_role, name, eks_cfg, eks_version, vpc, private_subnet_name, bastion_sg
        )

        cdk.CfnOutput(parent, "eks_cluster_name", value=self.cluster.cluster_name)
        cdk.CfnOutput(
            parent,
            "eks_kubeconfig_cmd",
            value=f"aws eks update-kubeconfig --name {self.cluster.cluster_name} --region {self.scope.region} --role-arn {self.cluster.kubectl_role.role_arn}",
        )
