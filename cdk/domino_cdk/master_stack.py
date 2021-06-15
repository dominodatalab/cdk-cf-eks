from aws_cdk import core as cdk
from yaml import dump as yaml_dump

from domino_cdk.agent import generate_install_config
from domino_cdk.config.base import DominoCDKConfig
from domino_cdk.efs_stack import DominoEfsProvisioner
from domino_cdk.eks_stack import DominoEksStack
from domino_cdk.s3_stack import DominoS3Provisioner
from domino_cdk.vpc_stack import DominoVpcProvisioner


class DominoMasterStack(cdk.Stack):
    def __init__(
        self, scope: cdk.Construct, construct_id: str, cfg: DominoCDKConfig, nest: bool = False, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.outputs = {}
        # The code that defines your stack goes here
        self.cfg = cfg
        self.env = kwargs["env"]
        self.name = self.cfg.name
        cdk.CfnOutput(self, "deploy_name", value=self.name)
        cdk.Tags.of(self).add("domino-deploy-id", self.name)
        for k, v in self.cfg.tags.items():
            cdk.Tags.of(self).add(str(k), str(v))

        self.s3_stack = DominoS3Provisioner(self, "S3Stack", self.name, self.cfg.s3, nest)
        self.vpc_stack = DominoVpcProvisioner(self, "VpcStack", self.name, self.cfg.vpc, nest)
        self.eks_stack = DominoEksStack(
            self,
            "EksStack",
            self.name,
            self.cfg.eks,
            self.vpc_stack.vpc,
            self.vpc_stack.private_subnet_name,
            self.vpc_stack.bastion_sg,
            self.cfg.route53.zone_ids,
            self.s3_stack.policy,
            nest,
        )
        self.efs_stack = DominoEfsProvisioner(
            self,
            "EfsSTack",
            self.name,
            self.cfg.efs,
            self.vpc_stack.vpc,
            self.eks_stack.cluster.cluster_security_group,
            nest,
        )
        cdk.CfnOutput(self, "agent_config", value=yaml_dump(generate_install_config(self)))
