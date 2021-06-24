from dataclasses import dataclass
from typing import Dict, List, Optional

from domino_cdk.config.util import MachineImage, check_leavins, from_loader


@dataclass
class EKS:
    """
    version: "1.19" - Kubernetes version for EKS cluster. _MUST BE A STRING_!
    private_api: true/false - Limits Kubernetes API access to the VPC. Access must be through a
                              bastion, peered network, or other in-VPC resource.
    max_nodegroup_azs: 3 - Will provision nodegroups in up to this many availability zones.
    global_node_labels: some-label: "true"  - Labels to apply to all kubernetes nodes
    global_node_tags: some-tags: "true"  - Labels to apply to all kubernetes nodes
    secrets_encryption_key_arn: ARN  - KMS key arn to encrypt kubernetes secrets. A new key will be created if omitted.
    """

    @dataclass
    class NodegroupBase:
        # Docs are combined since I haven't figured out a good way of placing them.
        # I would kind of prefer ng docs before managed, managed docs right below the
        # managed_nodegroups key, and the unmanaged similarly right below it. However,
        # configuring it this way seemed to place the empty managed value in the template
        # after the doc string for some bizarre reason. TODO. "..." is to prevent it from not
        # starting the empty lines with comments. Just personally bugs me.
        """
        Nodegroup Configuration:
        disk_size: 1000 - Size in GB for disk on nodes in nodegroup
        key_name: some-key-pair - Pre-existing AWS key pair to configure for instances in the nodegorup
        min_size: 1 - Minimum node count for nodegroup. Can't be 0 on managed nodegroups.
        max_size: 10 - Maximum limit for node count in node gorup
        machine_image: AMI and/or user_data script for nodes in nodegroup. When overriding AMI, you MUST
                       setup your custom AMI or your user_data script _MANUALLY_ to join the cluster.
                       Additionally, options that use user_data (ie ssm_agent) are no longer valid.
                       machine_image:
                         ami_id: ami-123abc
                         user_data: ...
        instance_types: ["m5.2xlarge", "m5.4xlarge"] - Instance types available to nodegroup
        labels: some-label: "true" - Labels to apply to all nodes in nodegroup
        tags: some-tag: "true" - Tags to apply to all nodes in nodegroup
        ...
        Managed nodegroup-specific options:
        spot: true/false - Use spot instances, may affect reliability/availability of nodegroup
        desired_size: 1 - Preferred size of nodegroup
        ...
        Unmanaged nodegroup-specific options:
        gpu: true/false - Setup GPU instance support
        ssm_agent: true/false - Install SSM agent (ie for console access via aws web ui)
        taints: some-taint: "true" - Taints to apply to all nodes in nodegroup
                                     ie to taint gpu nodes, etc.)
        """

        ssm_agent: bool
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
                "ssm_agent": ng.pop("ssm_agent"),
                "disk_size": ng.pop("disk_size"),
                "key_name": ng.pop("key_name", None),
                "min_size": ng.pop("min_size"),
                "max_size": ng.pop("max_size"),
                "machine_image": MachineImage(
                    ami_id=machine_image.pop("ami_id"), user_data=machine_image.pop("user_data")
                )
                if machine_image
                else None,
                "instance_types": ng.pop("instance_types"),
                "labels": ng.pop("labels"),
                "tags": ng.pop("tags"),
            }

    @dataclass
    class ManagedNodegroup(NodegroupBase):
        spot: bool
        desired_size: int

        @classmethod
        def load(cls, ng):
            out = cls(**cls.base_load(ng), spot=ng.pop("spot"), desired_size=ng.pop("desired_size"))
            check_leavins("managed nodegroup attribute", "config.eks.unmanaged_nodegroups", ng)
            return out

    @dataclass
    class UnmanagedNodegroup(NodegroupBase):
        gpu: bool
        taints: Dict[str, str]

        @classmethod
        def load(cls, ng):
            out = cls(**cls.base_load(ng), gpu=ng.pop("gpu"), taints=ng.pop("taints", {}))
            check_leavins("unmanaged nodegroup attribute", "config.eks.unmanaged_nodegroups", ng)
            return out

    version: str
    private_api: bool
    max_nodegroup_azs: int
    global_node_labels: Dict[str, str]
    global_node_tags: Dict[str, str]
    managed_nodegroups: Dict[str, ManagedNodegroup]
    unmanaged_nodegroups: Dict[str, UnmanagedNodegroup]
    secrets_encryption_key_arn: Optional[str]

    def __post_init__(self):
        errors = []

        def check_machine_image_exceptions(ng_name: str, mi: MachineImage, incompatible_options: bool = False):
            if mi.ami_id and not mi.user_data:
                errors.append(f"{ng_name}: User data must be provided when specifying a custom AMI")
            if mi.ami_id and incompatible_options:
                errors.append(
                    f"{ng_name}: ssm_agent, labels and taints cannot be automatically configured when specifying a custom AMI. "
                    "You need to configure all of this using user_data."
                )

        for name, ng in self.managed_nodegroups.items():
            error_name = f"Managed nodegroup [{name}]"
            if ng.machine_image:
                check_machine_image_exceptions(error_name, ng.machine_image, (ng.ssm_agent or ng.labels))
            if ng.min_size == 0:
                errors.append(
                    f"Error: {error_name} has min_size of 0. Only unmanaged nodegroups support min_size of 0."
                )
        for name, ng in self.unmanaged_nodegroups.items():
            error_name = f"Unmanaged nodegroup [{name}]"
            if ng.machine_image:
                check_machine_image_exceptions(error_name, ng.machine_image, (ng.ssm_agent or ng.labels or ng.taints))

        if errors:
            raise ValueError(errors)

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                private_api=c.pop("private_api"),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                global_node_tags=c.pop("global_node_tags"),
                managed_nodegroups={
                    name: EKS.ManagedNodegroup.load(ng) for name, ng in c.pop("managed_nodegroups", {}).items()
                },
                unmanaged_nodegroups={
                    name: EKS.UnmanagedNodegroup.load(ng) for name, ng in c.pop("nodegroups", {}).items()
                },
                secrets_encryption_key_arn=None,
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                private_api=c.pop("private_api"),
                secrets_encryption_key_arn=c.pop("secrets_encryption_key_arn", None),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                global_node_tags=c.pop("global_node_tags"),
                managed_nodegroups={
                    name: EKS.ManagedNodegroup.load(ng) for name, ng in c.pop("managed_nodegroups", {}).items()
                },
                unmanaged_nodegroups={
                    name: EKS.UnmanagedNodegroup.load(ng) for name, ng in c.pop("unmanaged_nodegroups", {}).items()
                },
            ),
            c,
        )
