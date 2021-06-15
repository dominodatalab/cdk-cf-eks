from aws_cdk import core as cdk
from yaml import dump as yaml_dump

from domino_cdk.config.base import DominoCDKConfig
from domino_cdk.efs_stack import DominoEfsStack
from domino_cdk.eks_stack import DominoEksStack
from domino_cdk.s3_stack import DominoS3Stack
from domino_cdk.util import DominoCdkUtil
from domino_cdk.vpc_stack import DominoVpcStack

manifests = [
    [
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    ]
]


class ExternalCommandException(Exception):
    """Exception running spawned external commands"""


class DominoMasterStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, cfg: DominoCDKConfig, **kwargs) -> None:
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

        self.s3_stack = DominoS3Stack(self, "S3Stack", self.name, self.cfg.s3)
        self.vpc_stack = DominoVpcStack(self, "VpcStack", self.name, self.cfg.vpc)
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
            self, "EfsSTack", self.name, self.cfg.efs, self.vpc_stack.vpc, self.eks_stack.cluster.cluster_security_group
        )
        cdk.CfnOutput(self, "agent_config", value=yaml_dump(self.generate_install_config()))

    # Override default max of 2 AZs, as well as allow configurability
    @property
    def availability_zones(self):
        return self.cfg.availability_zones or [
            cdk.Fn.select(0, cdk.Fn.get_azs(self.env.region)),
            cdk.Fn.select(1, cdk.Fn.get_azs(self.env.region)),
            cdk.Fn.select(2, cdk.Fn.get_azs(self.env.region)),
        ]

    def generate_install_config(self):
        agent_cfg = {
            "name": self.name,
            "pod_cidr": self.vpc_stack.vpc.vpc_cidr_block,
            "global_node_selectors": self.cfg.eks.global_node_labels,
            "storage_classes": {
                "shared": {
                    "efs": {
                        "region": self.cfg.aws_region,
                        "filesystem_id": self.efs_stack.outputs["efs"].value,
                    }
                },
            },
            "blob_storage": {
                "projects": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.s3_stack.buckets["blobs"].bucket_name,
                    },
                },
                "logs": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.s3_stack.buckets["logs"].bucket_name,
                    },
                },
                "backups": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.s3_stack.buckets["backups"].bucket_name,
                    },
                },
                "default": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.s3_stack.buckets["blobs"].bucket_name,
                    },
                },
            },
            "autoscaler": {
                "enabled": True,
                "auto_discovery": {
                    "cluster_name": self.eks_stack.cluster.cluster_name,
                },
                "groups": [],
                "aws": {
                    "region": self.cfg.aws_region,
                },
            },
            "internal_docker_registry": {
                "s3_override": {
                    "region": self.cfg.aws_region,
                    "bucket": self.s3_stack.buckets["registry"].bucket_name,
                }
            },
            "services": {
                "nginx_ingress": {},
                "nucleus": {
                    "chart_values": {
                        "keycloak": {
                            "createIntegrationTestUser": True,
                        }
                    }
                },
                "forge": {
                    "chart_values": {
                        "config": {
                            "fullPrivilege": True,
                        },
                    }
                },
            },
        }

        if self.cfg.route53.zone_ids:
            agent_cfg["external_dns"] = {
                "enabled": True,
                "zone_id_filters": self.cfg.route53.zone_ids,
                "txt_owner_id": self.eks_stack.outputs["route53-txt-owner-id"].value,
            }

        agent_cfg["services"]["nginx_ingress"]["chart_values"] = {
            "controller": {
                "kind": "Deployment",
                "hostNetwork": False,
                "config": {"use-proxy-protocol": "true"},
                "service": {
                    "enabled": True,
                    "type": "LoadBalancer",
                    "annotations": {
                        "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                        "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "tcp",
                        "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                        "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                        "service.beta.kubernetes.io/aws-load-balancer-proxy-protocol": "*",
                        # "service.beta.kubernetes.io/aws-load-balancer-security-groups":
                        #     "could-propagate-this-instead-of-create"
                    },
                    "targetPorts": {"http": "http", "https": "http"},
                    "loadBalancerSourceRanges": ["0.0.0.0/0"],  # TODO AF
                },
            }
        }

        return DominoCdkUtil.deep_merge(agent_cfg, self.cfg.install)
