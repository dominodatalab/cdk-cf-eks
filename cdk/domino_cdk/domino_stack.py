from typing import Optional

import aws_cdk.aws_s3 as s3
from aws_cdk import CfnOutput, Stack, Tags
from constructs import Construct

from domino_cdk.aws_configurator import DominoAwsConfigurator
from domino_cdk.config import DominoCDKConfig
from domino_cdk.provisioners import (
    DominoAcmProvisioner,
    DominoEfsProvisioner,
    DominoEksProvisioner,
    DominoS3Provisioner,
    DominoVpcProvisioner,
)
from domino_cdk.provisioners.eks.eks_iam_roles_for_k8s import (
    DominoEksK8sIamRolesProvisioner,
)
from domino_cdk.provisioners.lambda_utils import create_lambda
from domino_cdk.util import DominoCdkUtil


class DominoStack(Stack):
    acm_stack: Optional[DominoAcmProvisioner] = None
    efs_stack: Optional[DominoEfsProvisioner] = None
    s3_stack: Optional[DominoS3Provisioner] = None
    monitoring_bucket: Optional[s3.Bucket] = None

    def __init__(self, scope: Construct, construct_id: str, cfg: DominoCDKConfig, nest: bool = True, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        self.cfg = cfg
        self.env = kwargs["env"]
        self.name = self.cfg.name
        CfnOutput(self, "deploy_name", value=self.name)

        self.untagged_resources = {"ec2": [], "iam": []}

        for k, v in self.cfg.tags.items():
            Tags.of(self).add(str(k), str(v))

        if self.cfg.s3 is not None:
            self.s3_stack = DominoS3Provisioner(self, "S3Stack", self.name, self.cfg.s3, nest)
            self.monitoring_bucket = self.s3_stack.monitoring_bucket

        self.vpc_stack = DominoVpcProvisioner(
            self, "VpcStack", self.name, self.cfg.vpc, nest, monitoring_bucket=self.monitoring_bucket
        )

        self.eks_stack = DominoEksProvisioner(
            self,
            "EksStack",
            self.name,
            self.cfg.eks,
            self.vpc_stack.vpc,
            self.vpc_stack.private_subnet_name,
            self.vpc_stack.bastion_sg,
            self.cfg.route53.zone_ids if self.cfg.route53 is not None else [],
            nest,
            # Do not pass list of buckets to Eks provisioner if we are not using S3 access per node
            self.s3_stack.buckets
            if self.s3_stack is not None and cfg.create_iam_roles_for_service_accounts is False
            else [],
        )

        if cfg.create_iam_roles_for_service_accounts:
            DominoEksK8sIamRolesProvisioner(self).provision(self.name, self.eks_stack.cluster, self.s3_stack.buckets)

        if self.cfg.efs is not None:
            self.efs_stack = DominoEfsProvisioner(
                self,
                "EfsStack",
                self.name,
                self.cfg.efs,
                self.vpc_stack.vpc,
                self.eks_stack.cluster.cluster_security_group,
                nest,
            )

        if self.cfg.acm is not None:
            self.acm_stack = DominoAcmProvisioner(
                self,
                "AcmStack",
                self.name,
                self.cfg.acm,
                nest,
            )

        create_lambda(
            scope=self,
            stack_name=self.name,
            name="fix_missing_tags",
            properties={
                "stack_name": self.name,
                "tags": self.cfg.tags,
                "vpc_id": self.vpc_stack.vpc.vpc_id,
                "untagged_resources": self.untagged_resources,
            },
            resources=[
                "*",
            ],
            actions=[
                "ec2:CreateTags",
                "ec2:DescribeLaunchTemplates",
                "ec2:DescribeNetworkAcls",
                "ec2:DescribeRouteTables",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeVpcEndpoints",
                "iam:ListPolicies",
                "iam:TagPolicy",
            ],
        )

        # From 1.25 and on, you must maintain calico yourself
        if self.cfg.eks.version <= "1.24":
            # At least until we get the lambda working, this has to live in the eks stack's scope
            # as there is some implicit token used to construct the magically auto-generated kubectl
            # lambda behind the scenes when they are in separate stacks (nested or otehrwise).
            DominoAwsConfigurator(self.eks_stack.scope, self.eks_stack.cluster)
        else:
            CfnOutput(
                self,
                "zeCalicoNotice",  # ze puts the output at the end where it'll be seen
                value="Calico is no longer managed by CDK and has been uninstalled.. If upgrading from\n1.24 or earlier, you will have to manage Calico manually, or forgo network\npolicy enforcement.\n\nYou can reinstall Calico with the following command:\nhelm upgrade calico-tigera-operator tigera-operator \\\n--repo https://projectcalico.docs.tigera.io/charts --version v3.25.0 \\\n--namespace tigera-operator --set installation.kubernetesProvider=EKS \\\n--set installation.cni.type=AmazonVPC --set installation.registry=quay.io/ \\\n--timeout 10m --create-namespace --install\n\nIf you choose not to reinstall Calico, you should cycle all nodes.",
            )

        self.generate_outputs()

    def generate_outputs(self):
        if self.efs_stack is not None:
            CfnOutput(
                self,
                "EFSFilesystemId",
                value=self.efs_stack.efs.file_system_id,
            )
            CfnOutput(
                self,
                "EFSAccessPointId",
                value=self.efs_stack.efs_access_point.access_point_id,
            )

        if self.cfg.route53 is not None:
            r53_zone_ids = self.cfg.route53.zone_ids
            r53_owner_id = f"{self.name}CDK"
            CfnOutput(
                self,
                "route53-zone-id-output",
                value=str(r53_zone_ids),
            )
            CfnOutput(
                self,
                "route53-txt-owner-id",
                value=r53_owner_id,
            )

        CfnOutput(
            self,
            "agent_config",
            value="\"agent_config\" is no longer supported, please manually create your install configuration based on the provisioning outputs",
        )

        CfnOutput(self, "cdk_config", value=DominoCdkUtil.ruamel_dump(self.cfg.render(True)))
