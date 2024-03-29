from dataclasses import dataclass
from typing import Dict, List, TypeVar

from domino_cdk.config.util import check_leavins, from_loader


@dataclass
class EKS:
    """
    version: "1.21" - Kubernetes version for EKS cluster. _MUST BE A STRING_!
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
        availability_zones: Availability zones to greate subnets in. Leave this null to autogenerate.
        ami_id: ami-123abc - AMI to use for nodegroup, empty/null will default to the current EKS AMI.
                             When specifying an AMI, you MUST specify a custom user_data script to join
                             the node to the cluster, and this script must do any sort of node setup that
                             is desired. Additionally, some nodegroup options (ie labels, taints,
                             ssm_agent) are only allowed when using the default EKS AMI, as they may not
                             be compatible with other AMIs. When specifying an AMI, you must implement
                             those options manually via your user_data script.
        user_data: ... - Custom script for user_data, ran by cloud_init on node startup. When using the
                         default EKS AMI, this does not replace the default user_data. Your custom script
                         will be injected _before_ the default one, and both will be ran. However, when
                         specifying a custom AMI, this will be the *only* user_data script in use.
        instance_types: ["m5.2xlarge", "m5.4xlarge"] - Instance types available to nodegroup
        labels: some-label: "true" - Labels to apply to all nodes in nodegroup
        tags: some-tag: "true" - Tags to apply to all nodes in nodegroup
        ssm_agent: true/false - Install SSM agent (ie for console access via aws web ui)
        ...
        Managed nodegroup-specific options:
        spot: true/false - Use spot instances, may affect reliability/availability of nodegroup
        desired_size: 1 - Preferred size of nodegroup
        ...
        Unmanaged nodegroup-specific options:
        gpu: true/false - Setup GPU instance support
        taints: some-taint: "true" - Taints to apply to all nodes in nodegroup
                                     ie to taint gpu nodes, etc.)
        """

        ssm_agent: bool
        disk_size: int
        key_name: str
        min_size: int
        max_size: int
        availability_zones: List[str]
        ami_id: str
        user_data: str
        instance_types: List[str]
        labels: Dict[str, str]
        tags: Dict[str, str]
        spot: bool

        def base_load(ng):
            return {
                "ssm_agent": ng.pop("ssm_agent"),
                "disk_size": ng.pop("disk_size"),
                "key_name": ng.pop("key_name", None),
                "min_size": ng.pop("min_size"),
                "max_size": ng.pop("max_size"),
                "availability_zones": ng.pop("availability_zones", None),
                "ami_id": ng.pop("ami_id", None),
                "user_data": ng.pop("user_data", None),
                "instance_types": ng.pop("instance_types"),
                "labels": ng.pop("labels"),
                "tags": ng.pop("tags"),
                "spot": ng.pop("spot", False),
            }

    @dataclass
    class ManagedNodegroup(NodegroupBase):
        desired_size: int

        @classmethod
        def load(cls, ng):
            out = cls(**cls.base_load(ng), desired_size=ng.pop("desired_size"))
            check_leavins("managed nodegroup attribute", "config.eks.unmanaged_nodegroups", ng)
            return out

    @dataclass
    class UnmanagedNodegroup(NodegroupBase):
        gpu: bool
        imdsv2_required: bool
        taints: Dict[str, str]

        @classmethod
        def load(cls, ng):
            out = cls(
                **cls.base_load(ng),
                gpu=ng.pop("gpu"),
                imdsv2_required=ng.pop("imdsv2_required"),
                taints=ng.pop("taints", {}),
            )
            check_leavins("unmanaged nodegroup attribute", "config.eks.unmanaged_nodegroups", ng)
            return out

    version: str
    private_api: bool
    max_nodegroup_azs: int
    global_node_labels: Dict[str, str]
    global_node_tags: Dict[str, str]
    secrets_encryption_key_arn: str
    managed_nodegroups: Dict[str, ManagedNodegroup]
    unmanaged_nodegroups: Dict[str, UnmanagedNodegroup]

    def __post_init__(self):
        errors = []

        def check_ami_exceptions(ng_name: str, ami_id: str, user_data: str, incompatible_options: List[str] = None):
            if not ami_id:
                return

            if not user_data:
                errors.append(f"{ng_name}: User data must be provided when specifying a custom AMI")

            if incompatible_options and any(getattr(ng, opt) for opt in incompatible_options):
                options_msg = ", ".join(incompatible_options)
                errors.append(
                    f"{ng_name}: some options ({options_msg}) cannot be automatically configured when specifying a custom AMI. "
                    "Please set them to a false-y value (false, 0, \"\", {}, null) and then configure them in user_data or the AMI."
                )

        for name, ng in self.managed_nodegroups.items():
            error_name = f"Managed nodegroup [{name}]"
            check_ami_exceptions(error_name, ng.ami_id, ng.user_data, ["ssm_agent", "labels", "disk_size"])
            if ng.min_size == 0:
                errors.append(
                    f"Error: {error_name} has min_size of 0. Only unmanaged nodegroups support min_size of 0."
                )
            if ng.min_size > ng.desired_size:
                errors.append(
                    f"Error: {error_name} has a desired_size of {ng.desired_size}, which can't be less than the min_size (currently: {ng.min_size})."
                )
        for name, ng in self.unmanaged_nodegroups.items():
            error_name = f"Unmanaged nodegroup [{name}]"
            check_ami_exceptions(error_name, ng.ami_id, ng.user_data, ["ssm_agent", "labels", "taints", "disk_size"])

        if errors:
            raise ValueError(errors)

    @staticmethod
    def from_0_0_0(c: dict):
        def remap_mi(ng, unmanaged=False):
            if unmanaged:
                ng["imdsv2_required"] = False
                ng["spot"] = False
            return {**ng.pop("machine_image", {}), **ng}

        return from_loader(
            "config.eks",
            EKS(
                version=c.pop("version"),
                private_api=c.pop("private_api"),
                max_nodegroup_azs=c.pop("max_nodegroup_azs"),
                global_node_labels=c.pop("global_node_labels"),
                global_node_tags=c.pop("global_node_tags"),
                managed_nodegroups={
                    name: EKS.ManagedNodegroup.load(remap_mi(ng))
                    for name, ng in c.pop("managed_nodegroups", {}).items()
                },
                unmanaged_nodegroups={
                    name: EKS.UnmanagedNodegroup.load(remap_mi(ng, True))
                    for name, ng in c.pop("nodegroups", {}).items()
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


# This enables correct type checking for managed / unmanaged Nodegroups
T_NodegroupBase = TypeVar("T_NodegroupBase", bound=EKS.NodegroupBase)
