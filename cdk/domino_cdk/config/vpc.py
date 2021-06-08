from dataclasses import dataclass, is_dataclass
from typing import List

from domino_cdk.config.util import from_loader, IngressRule, MachineImage

@dataclass
class VPC:
    @dataclass
    class Bastion:
        enabled: bool
        key_name: str
        instance_type: str
        ingress_ports: List[IngressRule]
        machine_image: MachineImage

    id: str
    create: bool
    cidr: str
    max_azs: int
    bastion: Bastion

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.vpc",
            VPC(
                id=c.pop("id", None),
                create=c.pop("create"),
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
            c
        )

    @staticmethod
    def from_0_0_1(c: dict):
        bastion = c.pop("bastion")
        machine_image = bastion.pop("machine_image", None)
        return from_loader(
            "config.vpc",
            VPC(
                id=c.pop("id", None),
                create=c.pop("create"),
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
                    ) if machine_image else None
                )
            ),
            c
        )
