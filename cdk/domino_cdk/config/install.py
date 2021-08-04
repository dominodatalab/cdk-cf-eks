from dataclasses import dataclass
from typing import List

from domino_cdk.config.util import from_loader


@dataclass
class Install:
    """
    Values to pass to the Domino Installer (fleetcommand-agent).

    Quay credentials are for Domino's default public registry.
    Configuration for custom registries should be done via direct configuration of installer overrides.

    access_list: ["0.0.0.0/0", ...] - List of CIDRs that can access Domino's primary LoadBalancer
    acm_cert_arn: ARN - ARN of ACM SSL cert to be used for Domino install
    hostname: domino.example.com - Hostname of Domino install
    registry_username: some-username - Username for Domino quay.io image repositories
    registry_password: some-password - Password for Domino quay.io image repoistories
    overrides: <dict/hash> - Overrides of Domino Installer (fleetcommand-agent) configuration.
    """

    access_list: List[str]  # TODO: What should this variable be? cidr_access_list? loadbalancer_source_ranges?
    acm_cert_arn: str
    hostname: str
    registry_username: str
    registry_password: str
    overrides: dict
    istio_compatible: bool

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.install",
            Install(
                access_list=["0.0.0.0/0"],
                acm_cert_arn=None,
                hostname=None,
                registry_username=None,
                registry_password=None,
                istio_compatible=False,
                overrides=c,
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config.install",
            Install(
                access_list=c.pop("access_list"),
                acm_cert_arn=c.pop("acm_cert_arn"),
                hostname=c.pop("hostname"),
                registry_username=c.pop("registry_username"),
                registry_password=c.pop("registry_password"),
                overrides=c.pop("overrides"),
                istio_compatible=c.pop("istio_compatible", False),
            ),
            c,
        )
