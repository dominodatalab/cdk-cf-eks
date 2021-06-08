from dataclasses import dataclass, is_dataclass
from typing import Dict, List

from domino_cdk.config.util import from_loader, IngressRule, MachineImage

@dataclass
class EKS:
    @dataclass
    class NodegroupBase:
        disk_size: int
        key_name: str
        min_size: int
        max_size: int
        machine_image: MachineImage
        instance_types: List[str]
        labels: Dict[str, str]
        tags: Dict[str, str]

        def base_load(ng):
            machine_image = ng.pop("machine_image", None)
            return {
                "disk_size": ng.pop("disk_size"),
                "key_name": ng.pop("key_name", None),
                "min_size": ng.pop("min_size"),
                "max_size": ng.pop("max_size"),
                "machine_image": MachineImage(
                    ami_id=machine_image.pop("ami_id"),
                    user_data=machine_image.pop("user_data")
                ) if machine_image else None,
                "instance_types": ng.pop("instance_types"),
                "labels": ng.pop("labels"),
                "tags": ng.pop("tags")
                }

    @dataclass
    class ManagedNodegroup(NodegroupBase):
        spot: bool
        desired_size: int

        @classmethod
        def load(cls, ng):
            return cls(**cls.base_load(ng), spot=ng.pop("spot"), desired_size=ng.pop("desired_size"))


    @dataclass
    class UnmanagedNodegroup(NodegroupBase):
        gpu: bool
        ssm_agent: bool
        taints: Dict[str, str]

        @classmethod
        def load(cls, ng):
            return cls(**cls.base_load(ng), gpu=ng.pop("gpu"), ssm_agent=ng.pop("ssm_agent"), taints=ng.pop("taints", {}))

    version: str
    private_api: bool
    max_nodegroup_azs: int
    global_node_labels: Dict[str, str]
    managed_nodegroups: Dict[str, ManagedNodegroup]
    unmanaged_nodegroups: Dict[str, UnmanagedNodegroup]

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                private_api=c.pop("private_api"),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                managed_nodegroups={name: EKS.ManagedNodegroup.load(ng) for name, ng in c.pop("managed_nodegroups", {}).items()},
                unmanaged_nodegroups={name: EKS.UnmanagedNodegroup.load(ng) for name, ng in c.pop("nodegroups", {}).items()},
            ),
            c
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                private_api=c.pop("private_api"),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                managed_nodegroups={name: EKS.ManagedNodegroup.load(ng) for name, ng in c.pop("managed_nodegroups", {}).items()},
                unmanaged_nodegroups={name: EKS.UnmanagedNodegroup.load(ng) for name, ng in c.pop("unmanaged_nodegroups", {}).items()},
            ),
            c
        )
