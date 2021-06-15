from semantic_version import Version

from domino_cdk import __version__
from domino_cdk.config.base import DominoCDKConfig
from domino_cdk.config.eks import EKS


def config_loader(c: dict):
    schema = Version(c.pop("schema", "0.0.0")).truncate()
    loader = getattr(DominoCDKConfig, f"from_{schema}".replace(".", "_"), None)
    if not loader:
        raise ValueError(f"Unsupported schema version: {schema}")
    return loader(c)


def config_template(platform_nodegroups: int, compute_nodegroups: int, gpu_nodegroups: int, bastion: bool = False, private_api: bool = False, dev_defaults: bool = False):

    unmanaged_nodegroups = []
    for i in range(0, platform_nodegroups):
        unmanaged_nodegroups.append(EKS.UnmanagedNodegroup(
            gpu=False,
            ssm_agent=True,
            disk_size=100,
            key_name=None,
            min_size=1,
            max_size=10,
            machine_image=None,
            instance_types=["m4.2xlarge"],
            labels={"dominodatalab.com/node-pool": "platform"},
            tags={},
            taints={}
        ))

    max_nodegroup_azs = 3
    destroy_on_destroy = False
    disk_size = 1000
    platform_instance_type = "m5.2xlarge"
    platform_min_size = 3
    if dev_defaults:
        max_nodegroup_azs = 1
        destroy_on_destroy = True
        disk_size = 100
        platform_instance_type = "m5.4xlarge"
        platform_min_size = 1
    return config_loader(
        {
            "schema": __version__,
            "name": "domino",
            "aws_region": "__FILL__",
            "aws_account_id": "__FILL__",
            "tags": {"domino-infrastructure": "true"},
            "vpc": {
                "id": None,
                "create": True,
                "cidr": "10.0.0.0/16",
                "max_azs": 3,
                "availability_zones": [],
                "bastion": {
                    "enabled": bastion,
                    "instance_type": "t2.micro",
                    "ingress_ports": [
                        {"name": "ssh", "from_port": 22, "to_port": 22, "protocol": "TCP", "ip_cidrs": ["0.0.0.0/0"]}
                    ],
                },
            },
            "efs": {
                "removal_policy_destroy": destroy_on_destroy,
                "backup": {
                    "enable": True,
                    "schedule": "0 12 * * ? *",
                    "move_to_cold_storage_after": 35,
                    "delete_after": 125,
                    "removal_policy": "DESTROY" if destroy_on_destroy else False,
                },
            },
            "route53": {"zone_ids": []},
            "eks": {
                "version": "1.19",
                "private_api": private_api,
                "max_nodegroup_azs": max_nodegroup_azs,
                "global_node_labels": {"dominodatalab.com/domino-node": "true"},
                "global_node_tags": {},
                "managed_nodegroups": {},
                "unmanaged_nodegroups": {
                    "platform": {
                        "gpu": False,
                        "ssm_agent": True,
                        "disk_size": disk_size,
                        "min_size": platform_min_size,
                        "max_size": 10,
                        "instance_types": [platform_instance_type],
                        "labels": {"dominodatalab.com/node-pool": "platform"},
                        "tags": {},
                    },
                    "compute": {
                        "gpu": False,
                        "ssm_agent": True,
                        "disk_size": disk_size,
                        "min_size": 0,
                        "max_size": 10,
                        "instance_types": ["m5.2xlarge"],
                        "labels": {"dominodatalab.com/node-pool": "default", "domino/build-node": "true"},
                        "tags": {},
                    },
                    "nvidia": {
                        "gpu": True,
                        "ssm_agent": True,
                        "disk_size": disk_size,
                        "min_size": 0,
                        "max_size": 10,
                        "instance_types": ["m5.2xlarge"],
                        "taints": {"nvidia.com/gpu": "true:NoSchedule"},
                        "labels": {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
                        "tags": {},
                    },
                },
            },
            "s3": {
                "buckets": {
                    "blobs": {"auto_delete_objects": destroy_on_destroy, "removal_policy_destroy": destroy_on_destroy},
                    "logs": {"auto_delete_objects": destroy_on_destroy, "removal_policy_destroy": destroy_on_destroy},
                    "backups": {
                        "auto_delete_objects": destroy_on_destroy,
                        "removal_policy_destroy": destroy_on_destroy,
                    },
                    "registry": {
                        "auto_delete_objects": destroy_on_destroy,
                        "removal_policy_destroy": destroy_on_destroy,
                    },
                }
            },
            "install": {},
        }
    )
