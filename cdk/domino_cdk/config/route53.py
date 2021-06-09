from dataclasses import dataclass
from typing import List

from domino_cdk.config.util import from_loader


@dataclass
class Route53:
    """zone_ids: ["ABCDEFG123"] - List of Route53 Zone IDs to add to cluster IAM policy for
    cloud integration (ie external-dns)."""

    zone_ids: List[str]

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader("config.route53", Route53(zone_ids=c.pop("zone_ids", None)), c)
