from semantic_version import Version

from domino_cdk import __version__
from domino_cdk.config.base import DominoCDKConfig


def config_loader(c: dict):
    schema = Version(c.pop("schema", "0.0.0")).truncate()
    if schema == Version("0.0.1"):
        return DominoCDKConfig.from_0_0_1(c)
    elif schema == Version("0.0.0"):
        return DominoCDKConfig.from_0_0_0(c)


def config_template():
    return config_loader(
        {
            "schema": __version__,
            "name": "domino",
            "aws_region": "__FILL__",
            "aws_account_id": "__FILL__",
            "availability_zones": [],
            "tags": {"domino-infrastructure": "true"},
            "vpc": {
                "id": None,
                "create": True,
                "cidr": "10.0.0.0/16",
                "max_azs": 3,
                "bastion": {
                    "enabled": True,
                    "instance_type": "t2.micro",
                    "ingress_ports": [
                        {"name": "ssh", "from_port": 22, "to_port": 22, "protocol": "TCP", "ip_cidrs": ["0.0.0.0/0"]}
                    ],
                },
            },
            "efs": {
#                "removal_policy_destroy": True,
                "backup": {
                    "enable": True,
                    "schedule": "0 12 * * ? *",
                    "move_to_cold_storage_after": 35,
                    "delete_after": 125,
                    "removal_policy": "DESTROY",
                },
            },
            "route53": {"zone_ids": []},
            "eks": {
                "version": 1.19,
                "private_api": True,
                "max_nodegroup_azs": 1,
                "global_node_labels": {"dominodatalab.com/domino-node": "true"},
                "managed_nodegroups": {},
                "unmanaged_nodegroups": {
                    "platform": {
                        "gpu": False,
                        "ssm_agent": True,
                        "disk_size": 100,
                        "min_size": 1,
                        "max_size": 10,
                        "instance_types": ["m5.2xlarge"],
                        "labels": {"dominodatalab.com/node-pool": "platform"},
                        "tags": {"dominodatalab.com/node-pool": "platform"},
                    },
                    "compute": {
                        "gpu": False,
                        "ssm_agent": True,
                        "disk_size": 100,
                        "min_size": 0,
                        "max_size": 10,
                        "instance_types": ["m5.2xlarge"],
                        "labels": {"dominodatalab.com/node-pool": "default", "domino/build-node": "true"},
                        "tags": {"dominodatalab.com/node-pool": "default", "domino/build-node": "true"},
                    },
                    "nvidia": {
                        "gpu": True,
                        "ssm_agent": True,
                        "disk_size": 100,
                        "min_size": 0,
                        "max_size": 10,
                        "instance_types": ["m5.2xlarge"],
                        "taints": {"nvidia.com/gpu": "true:NoSchedule"},
                        "labels": {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
                        "tags": {"dominodatalab.com/node-pool": "default-gpu"},
                    },
                },
            },
            "s3": {
                "buckets": {
                    "blobs": {"auto_delete_objects": False, "removal_policy_destroy": False},
                    "logs": {"auto_delete_objects": False, "removal_policy_destroy": False},
                    "backups": {"auto_delete_objects": False, "removal_policy_destroy": False},
                    "registry": {"auto_delete_objects": False, "removal_policy_destroy": False},
                }
            },
            "install": {},
        }
    )
