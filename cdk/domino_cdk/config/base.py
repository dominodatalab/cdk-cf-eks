from dataclasses import dataclass, is_dataclass
from inspect import isclass
from typing import Dict, List

from domino_cdk import __version__
from domino_cdk.config.efs import EFS
from domino_cdk.config.eks import EKS
from domino_cdk.config.route53 import Route53
from domino_cdk.config.s3 import S3
from domino_cdk.config.vpc import VPC


def from_loader(name: str, cfg, c: dict):
    if c:
        print(f"Warning: Unused/unsupported config entries in {name}: {c}")
    return cfg


@dataclass
class MachineImage:
    ami_id: str
    user_data: str


@dataclass
class DominoCDKConfig:
    name: str
    aws_region: str
    aws_account_id: str
    availability_zones: List[str]
    tags: Dict[str, str]
    install: dict

    vpc: VPC
    efs: EFS
    route53: Route53
    eks: EKS
    s3: S3

    schema: str = __version__

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
                name=c.pop("name"),
                aws_region=c.pop("aws_region"),
                aws_account_id=c.pop("aws_account_id"),
                availability_zones=c.pop("availability_zones", []),
                tags=c.pop("tags", {}),
                install=c.pop("install", {}),
                vpc=VPC.from_0_0_0(c.pop("vpc")),
                efs=EFS.from_0_0_1(c.pop("efs")),
                route53=Route53.from_0_0_1(c.pop("route53")),
                eks=EKS.from_0_0_0(c.pop("eks")),
                s3=S3.from_0_0_0(c.pop("s3")),
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
                name=c.pop("name"),
                aws_region=c.pop("aws_region"),
                aws_account_id=c.pop("aws_account_id"),
                availability_zones=c.pop("availability_zones", []),
                tags=c.pop("tags", {}),
                install=c.pop("install", {}),
                vpc=VPC.from_0_0_1(c.pop("vpc")),
                efs=EFS.from_0_0_1(c.pop("efs")),
                route53=Route53.from_0_0_1(c.pop("route53")),
                eks=EKS.from_0_0_1(c.pop("eks")),
                s3=S3.from_0_0_0(c.pop("s3")),
            ),
            c,
        )

    def render(self):
        def r_vars(c):
            if is_dataclass(c):
                return {x: r_vars(y) for x, y in vars(c).items()}
            else:
                return c

        return r_vars(self)