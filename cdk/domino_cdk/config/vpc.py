from dataclasses import dataclass
from typing import List

from domino_cdk.config.util import IngressRule, MachineImage, from_loader


@dataclass
class VPC:
    """
    create: true/false - Either create a VPC, or use an existing one
    id: vpc-abc123 - VPC id when using an existing VPC
    cidr: 10.0.0.0/16 - Primary CIDR range for VPC
                        NOTE: EKS needs _lots_ of IPs
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
        machine_image: AMI and/or user_data script for the bastion
                       machine_image:
                         ami_id: ami-123abc
                         user_data: ...
        """

        enabled: bool
        key_name: str
        instance_type: str
        ingress_ports: List[IngressRule]
        machine_image: MachineImage

    create: bool
    id: str
    cidr: str
    max_azs: int
    bastion: Bastion

    def __post_init__(self):
        if not self.id and not self.create:
            raise ValueError("Error: Cannot provision into a VPC. Must either create a vpc or provide an existing one")
        if self.max_azs < 2:
            raise ValueError("Error: Must use at least two availability zones with EKS")
        # The "or" is covering the case of user_data provided without ami_id
        if self.bastion.enabled and self.bastion.machine_image and not self.bastion.machine_image.ami_id:
            raise ValueError("Error: Bastion instance with user_data requires an ami_id!")

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.vpc",
            VPC(
                create=c.pop("create"),
                id=c.pop("id", None),
                cidr=c.pop("cidr"),
                max_azs=c.pop("max_azs"),
                bastion=VPC.Bastion(
                    enabled=False,
                    key_name=None,
                    instance_type=None,
                    ingress_ports=None,
                    machine_image=None,
                ),
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        bastion = c.pop("bastion")
        machine_image = bastion.pop("machine_image", None)
        return from_loader(
            "config.vpc",
            VPC(
                create=c.pop("create"),
                id=c.pop("id", None),
                cidr=c.pop("cidr"),
                max_azs=c.pop("max_azs"),
                bastion=VPC.Bastion(
                    enabled=bastion.pop("enabled"),
                    key_name=bastion.pop("key_name", None),
                    instance_type=bastion.pop("instance_type"),
                    ingress_ports=IngressRule.load_rules("config.vpc.bastion", bastion.pop("ingress_ports")),
                    machine_image=MachineImage(
                        ami_id=machine_image.pop("ami_id"),
                        user_data=machine_image.pop("user_data"),
                    )
                    if machine_image
                    else None,
                ),
            ),
            c,
        )
