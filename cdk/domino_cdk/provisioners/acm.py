import aws_cdk.aws_certificatemanager as acm
import aws_cdk.aws_route53 as route53
from aws_cdk import NestedStack
from constructs import Construct

from domino_cdk import config


class DominoAcmProvisioner:
    def __init__(
        self,
        parent: Construct,
        construct_id: str,
        stack_name: str,
        cfg: config.ACM,
        nest: bool,
        **kwargs,
    ):
        self.parent = parent
        self.scope = NestedStack(self.parent, construct_id, **kwargs) if nest else self.parent

        self.provision_acm(stack_name, cfg)

    def provision_acm(self, stack_name: str, cfg: config.ACM):
        self.acm_certs = [self.create_cert(index, cert) for index, cert in enumerate(cfg.certificates)]

    def create_cert(self, index: int, c: config.ACM.Certificate):
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self.scope, f"HostedZone{index}", zone_name=c.zone_name, hosted_zone_id=c.zone_id
        )
        acm.Certificate(
            self.scope,
            f"Certificate{index}",
            domain_name=c.domain,
            subject_alternative_names=[f"*.{c.domain}"],
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )
