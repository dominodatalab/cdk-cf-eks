from aws_cdk import core as cdk

from domino_cdk.agent import generate_install_config
from domino_cdk.aws_configurator import DominoAwsConfigurator
from domino_cdk.config import DominoCDKConfig
from domino_cdk.provisioners import (
    DominoEfsProvisioner,
    DominoEksProvisioner,
    DominoS3Provisioner,
    DominoVpcProvisioner,
)
from domino_cdk.provisioners.eks.eks_iam_roles_for_k8s import (
    DominoEksK8sIamRolesProvisioner,
)
from domino_cdk.util import DominoCdkUtil


class DominoStack(cdk.Stack):
    def __init__(
        self, scope: cdk.Construct, construct_id: str, cfg: DominoCDKConfig, nest: bool = True, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        self.cfg = cfg
        self.env = kwargs["env"]
        self.name = self.cfg.name
        cdk.CfnOutput(self, "deploy_name", value=self.name)
        for k, v in self.cfg.tags.items():
            cdk.Tags.of(self).add(str(k), str(v))

        self.s3_stack = DominoS3Provisioner(self, "S3Stack", self.name, self.cfg.s3, nest)

        self.vpc_stack = DominoVpcProvisioner(
            self, "VpcStack", self.name, self.cfg.vpc, nest, monitoring_bucket=self.s3_stack.monitoring_bucket
        )

        self.eks_stack = DominoEksProvisioner(
            self,
            "EksStack",
            self.name,
            self.cfg.eks,
            self.vpc_stack.vpc,
            self.vpc_stack.private_subnet_name,
            self.vpc_stack.bastion_sg,
            self.cfg.route53.zone_ids,
            nest,
            # Do not pass list of buckets to Eks provisioner if we are not using S3 access per node
            self.s3_stack.buckets if cfg.create_iam_roles_for_service_accounts is False else [],
        )

        if cfg.create_iam_roles_for_service_accounts:
            DominoEksK8sIamRolesProvisioner(self).provision(self.name, self.eks_stack.cluster, self.s3_stack.buckets)

        self.efs_stack = DominoEfsProvisioner(
            self,
            "EfsStack",
            self.name,
            self.cfg.efs,
            self.vpc_stack.vpc,
            self.eks_stack.cluster.cluster_security_group,
            nest,
        )
        # At least until we get the lambda working, this has to live in the eks stack's scope
        # as there is some implicit token used to construct the magically auto-generated kubectl
        # lambda behind the scenes when they are in separate stacks (nested or otehrwise).
        DominoAwsConfigurator(self.eks_stack.scope, self.eks_stack.cluster, self.vpc_stack.vpc)

        self.generate_outputs()

    def generate_outputs(self):
        efs_fs_ap_id = f"{self.efs_stack.efs.file_system_id}::{self.efs_stack.efs_access_point.access_point_id}"
        r53_zone_ids = self.cfg.route53.zone_ids
        r53_owner_id = f"{self.name}CDK"

        cdk.CfnOutput(
            self,
            "efs-output",
            value=efs_fs_ap_id,
        )

        if r53_zone_ids:
            cdk.CfnOutput(
                self,
                "route53-zone-id-output",
                value=str(r53_zone_ids),
            )
            cdk.CfnOutput(
                self,
                "route53-txt-owner-id",
                value=r53_owner_id,
            )

        agent_cfg = generate_install_config(
            name=self.name,
            aws_region=self.cfg.aws_region,
            eks_cluster_name=self.eks_stack.cluster.cluster_name,
            pod_cidr=self.vpc_stack.vpc.vpc_cidr_block,
            global_node_selectors=self.cfg.eks.global_node_labels,
            buckets=self.s3_stack.buckets,
            monitoring_bucket=self.s3_stack.monitoring_bucket,
            efs_fs_ap_id=efs_fs_ap_id,
            r53_zone_ids=r53_zone_ids,
            r53_owner_id=r53_owner_id,
        )

        merged_cfg = DominoCdkUtil.deep_merge(agent_cfg, self.cfg.install)

        cdk.CfnOutput(self, "agent_config", value=DominoCdkUtil.ruamel_dump(merged_cfg))
        cdk.CfnOutput(self, "cdk_config", value=DominoCdkUtil.ruamel_dump(self.cfg.render(True)))
