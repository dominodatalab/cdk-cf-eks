from dataclasses import dataclass
from typing import List, Optional

from domino_cdk.config.util import from_loader


@dataclass
class ACM:
    @dataclass
    class Certificate:
        """
        domain: Name of domain to create the certificate for
        zone_name: Zone to use for DNS validation
        """

        domain: str
        zone_name: str

    certificates: List[Certificate]

    @staticmethod
    def from_0_0_0(c: dict) -> Optional['ACM']:
        certificates = c.pop("certificates")
        return from_loader(
            "config.acm",
            ACM(
                certificates=[ACM.Certificate(cert.pop("domain"), cert.pop("zone_name")) for cert in certificates]
            ),
            c,
        )
