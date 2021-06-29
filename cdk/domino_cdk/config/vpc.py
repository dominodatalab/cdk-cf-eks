from dataclasses import dataclass
from typing import List

from domino_cdk.config.util import IngressRule, from_loader


@dataclass
class VPC:
    """
    create: true/false - Either create a VPC, or use an existing one
    id: vpc-abc123 - VPC id when using an existing VPC
    cidr: 10.0.0.0/16 - Primary CIDR range for VPC
                        NOTE: EKS needs _lots_ of IPs
    availability_zones: Specific availability zones to use with vpc (optional)
    max_azs: 3 - Maximum amount of availability zones to configure for the VPC
                 MUST have at least two for the EKS control plane to provision
    """

    @dataclass
    class Bastion:
        """
        enabled: true/false - Provision a bastion. If config.eks.private_api is true,
                              you may need this to access your cluster.
        key_name: some-key-pair - Pre-existing AWS key pair to configure for the bastion
                                  instance. [Optional]
        instance_type: t2.micro, etc.
        ingress_ports: list of ingress rules in the following format:
                       - name: ssh
                         from_port: 22
                         to_port: 22
                         protocol: TCP
                         ip_cidrs:
                         - 0.0.0.0/0
                       (customizing cidrs aside, this would be the most common rule for this)
        ami_id: ami-123abc - AMI to use for the bastion. Defaults to ubuntu.
        user_data: ... - user_data to use to setup the bastion. Default: blank
        """

        enabled: bool
        key_name: str
        instance_type: str
        ingress_ports: List[IngressRule]
        ami_id: str
        user_data: str

    create: bool
    id: str
    cidr: str
    availability_zones: List[str]
    max_azs: int
    bastion: Bastion

    def __post_init__(self):
        if not self.id and not self.create:
            raise ValueError("Error: Cannot provision into a VPC. Must either create a vpc or provide an existing one")
        if self.max_azs < 2:
            raise ValueError("Error: Must use at least two availability zones with EKS")
        if self.bastion.enabled and not self.bastion.ami_id and self.bastion.user_data:
            raise ValueError("Error: Bastion instance with user_data requires an ami_id!")

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.vpc",
            VPC(
                create=c.pop("create"),
                id=c.pop("id", None),
                cidr=c.pop("cidr"),
                availability_zones=c.pop("availability_zones", []),
                max_azs=c.pop("max_azs"),
                bastion=VPC.Bastion(
                    enabled=False,
                    key_name=None,
                    instance_type=None,
                    ingress_ports=None,
                    ami_id=None,
                    user_data=None,
                ),
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        bastion = c.pop("bastion")
        return from_loader(
            "config.vpc",
            VPC(
                create=c.pop("create"),
                id=c.pop("id", None),
                cidr=c.pop("cidr"),
                availability_zones=c.pop("availability_zones", []),
                max_azs=c.pop("max_azs"),
                bastion=VPC.Bastion(
                    enabled=bastion.pop("enabled"),
                    key_name=bastion.pop("key_name", None),
                    instance_type=bastion.pop("instance_type"),
                    ingress_ports=IngressRule.load_rules("config.vpc.bastion", bastion.pop("ingress_ports")),
                    ami_id=bastion.pop("ami_id", None),
                    user_data=bastion.pop("user_data", None),
                ),
            ),
            c,
        )
