import aws_cdk.aws_certificatemanager as acm
import aws_cdk.aws_route53 as route53
from aws_cdk import core as cdk

from domino_cdk import config

from .lambda_utils import create_lambda

_DominoAcmStack = None


class DominoAcmProvisioner:
    def __init__(
        self,
        parent: cdk.Construct,
        construct_id: str,
        stack_name: str,
        cfg: config.ACM,
        nest: bool,
        **kwargs,
    ):
        self.parent = parent
        self.scope = cdk.NestedStack(self.parent, construct_id, **kwargs) if nest else self.parent

        self.provision_acm(stack_name, cfg)

    def provision_efs(self, stack_name: str, cfg: config.ACM):
        self.acm_certs = [ create_cert(cert) for cert in cfg.certificates ]

    def create_cert(c: config.ACM.Certificate):
        if c.zone_name is None:
          return acm.Certificate(self, "Certificate",
            domain_name = c.domain,
            subject_alternative_names=[f"*.{c.domain}"],
            validation=acm.CertificateValidation.from_dns()
          )
        else:
          hosted_zone = route53.HostedZone(self, "HostedZone",
              zone_name=c.zone_name
          )
          acm.Certificate(self, "Certificate",
              domain_name = c.domain,
              subject_alternative_names=[f"*.{c.domain}"],
              validation=acm.CertificateValidation.from_dns(hosted_zone)
          )
