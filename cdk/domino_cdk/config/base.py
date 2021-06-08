from dataclasses import dataclass, is_dataclass
from inspect import isclass

from domino_cdk import __version__
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
    aws_region: str
    aws_account_id: str
    tags: dict
    install: dict

    vpc: VPC
    #efs: EFS
    #route53: Route53
    #eks: EKS
    #s3: S3

    schema: str = __version__

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
            aws_region=c.pop("aws_region"),
            aws_account_id=c.pop("aws_account_id"),
            tags=c.pop("tags", {}),
            install=c.pop("install", {}),
            vpc=VPC.from_0_0_0(c.pop("vpc"))
            ),
            c
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
            aws_region=c.pop("aws_region"),
            aws_account_id=c.pop("aws_account_id"),
            tags=c.pop("tags", {}),
            install=c.pop("install", {}),
            vpc=VPC.from_0_0_1(c.pop("vpc"))
            ),
            c
        )

    def render(self):
        def r_vars(c):
            if is_dataclass(c):
                return {x: r_vars(y) for x, y in vars(c).items()}
            else:
                return c
        return r_vars(self)



