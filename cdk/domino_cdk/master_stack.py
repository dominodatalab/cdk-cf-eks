from aws_cdk import core as cdk
from yaml import dump as yaml_dump

from domino_cdk.agent import generate_install_config
from domino_cdk.config.base import DominoCDKConfig
from domino_cdk.efs_stack import DominoEfsStack
from domino_cdk.eks_stack import DominoEksStack
from domino_cdk.s3_stack import DominoS3Stack
from domino_cdk.vpc_stack import DominoVpcStack


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

        self.s3_stack = DominoS3Stack(nest, self, "S3Stack", self.name, self.cfg.s3)
        self.vpc_stack = DominoVpcStack(nest, self, "VpcStack", self.name, self.cfg.vpc)
        self.eks_stack = DominoEksStack(
            self,
            "EksStack",
            self.name,
            self.cfg.eks,
            vpc=self.vpc_stack.vpc,
            private_subnet_name=self.vpc_stack.private_subnet_name,
            bastion_sg=self.vpc_stack.bastion_sg,
            r53_zone_ids=self.cfg.route53.zone_ids,
            s3_policy=self.s3_stack.policy,
        )
        self.efs_stack = DominoEfsStack(
            nest,
            self,
            "EfsSTack",
            self.name,
            self.cfg.efs,
            self.vpc_stack.vpc,
            self.eks_stack.cluster.cluster_security_group,
        )
        cdk.CfnOutput(self, "agent_config", value=yaml_dump(generate_install_config(self)))
