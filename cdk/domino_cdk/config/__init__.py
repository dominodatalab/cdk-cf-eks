from typing import Optional

from semantic_version import Version

from domino_cdk import __version__
from domino_cdk.config.base import DominoCDKConfig
from domino_cdk.config.efs import EFS
from domino_cdk.config.eks import EKS
from domino_cdk.config.route53 import Route53
from domino_cdk.config.s3 import S3
from domino_cdk.config.util import IngressRule, MachineImage
from domino_cdk.config.vpc import VPC


def config_loader(c: dict):
    schema = Version(c.pop("schema", "0.0.0")).truncate()
    loader = getattr(DominoCDKConfig, f"from_{schema}".replace(".", "_"), None)
    if not loader:
        raise ValueError(f"Unsupported schema version: {schema}")
    return loader(c)
