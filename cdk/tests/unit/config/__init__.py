import unittest
from unittest.mock import patch

from domino_cdk.config import (
    EFS,
    EKS,
    S3,
    VPC,
    DominoCDKConfig,
    IngressRule,
    Install,
    Route53,
    config_loader,
)
from domino_cdk.config.template import config_template

default_config = DominoCDKConfig(
    name='domino',
    aws_region='__FILL__',
    aws_account_id='__FILL__',
    tags={'domino-infrastructure': 'true'},
    install=Install(
        access_list=["0.0.0.0/0"],
        acm_cert_arn=None,
        hostname=None,
        registry_username=None,
        registry_password=None,
        istio_compatible=False,
        overrides={},
    ),
    vpc=VPC(
        id=None,
        create=True,
        cidr='10.0.0.0/16',
        public_cidr_mask=27,
        private_cidr_mask=19,
        availability_zones=[],
        max_azs=3,
        flow_logging=True,
        endpoints=True,
        bastion=VPC.Bastion(
            enabled=False,
            key_name=None,
            instance_type='t2.micro',
            ingress_ports=[IngressRule(name='ssh', from_port=22, to_port=22, protocol='TCP', ip_cidrs=['0.0.0.0/0'])],
            ami_id=None,
            user_data=None,
        ),
    ),
    efs=EFS(
        backup=EFS.Backup(
            enable=True,
            schedule='0 12 * * ? *',
            move_to_cold_storage_after=35,
            delete_after=125,
            removal_policy=False,
        ),
        removal_policy_destroy=False,
    ),
    route53=Route53(zone_ids=[]),
    eks=EKS(
        version="1.21",
        private_api=False,
        max_nodegroup_azs=3,
        global_node_labels={'dominodatalab.com/domino-node': 'true'},
        global_node_tags={},
        managed_nodegroups={},
        unmanaged_nodegroups={
            'platform-0': EKS.UnmanagedNodegroup(
                disk_size=100,
                key_name=None,
                min_size=1,
                max_size=10,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=['m5.2xlarge'],
                labels={'dominodatalab.com/node-pool': 'platform'},
                tags={},
                gpu=False,
                imdsv2_required=True,
                ssm_agent=True,
                taints={},
                spot=False,
            ),
            'compute-0': EKS.UnmanagedNodegroup(
                disk_size=1000,
                key_name=None,
                min_size=0,
                max_size=10,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=['m5.2xlarge'],
                labels={'dominodatalab.com/node-pool': 'default'},
                tags={},
                gpu=False,
                imdsv2_required=True,
                ssm_agent=True,
                taints={},
                spot=False,
            ),
            'gpu-0': EKS.UnmanagedNodegroup(
                disk_size=1000,
                key_name=None,
                min_size=0,
                max_size=10,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=['p3.2xlarge'],
                labels={'dominodatalab.com/node-pool': 'default-gpu', 'nvidia.com/gpu': 'true'},
                tags={},
                gpu=True,
                imdsv2_required=True,
                ssm_agent=True,
                taints={'nvidia.com/gpu': 'true:NoSchedule'},
                spot=False,
            ),
        },
        secrets_encryption_key_arn=None,
    ),
    s3=S3(
        buckets=S3.BucketList(
            blobs=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            logs=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            backups=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            registry=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            monitoring=S3.BucketList.Bucket(
                auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None
            ),
        )
    ),
    schema='0.0.2',
)

legacy_template = {
    "schema": "0.0.0",
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
            "enabled": False,
            "instance_type": None,
            "ingress_ports": None,
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
        "version": "1.19",
        "private_api": True,
        "max_nodegroup_azs": 1,
        "global_node_labels": {"dominodatalab.com/domino-node": "true"},
        "global_node_tags": {"k8s.io/cluster-autoscaler/node-template/label/dominodatalab.com/domino-node": "true"},
        "managed_nodegroups": {},
        "nodegroups": {
            "platform-0": {
                "gpu": False,
                "ssm_agent": True,
                "disk_size": 100,
                "min_size": 1,
                "max_size": 10,
                "instance_types": ["m5.2xlarge"],
                "labels": {"dominodatalab.com/node-pool": "platform"},
                "tags": {"dominodatalab.com/node-pool": "platform"},
            },
            "compute-0": {
                "gpu": False,
                "ssm_agent": True,
                "disk_size": 100,
                "min_size": 1,
                "max_size": 10,
                "instance_types": ["m5.2xlarge"],
                "labels": {"dominodatalab.com/node-pool": "default", "domino/build-node": "true"},
                "tags": {"dominodatalab.com/node-pool": "default", "domino/build-node": "true"},
            },
            "gpu-0": {
                "gpu": True,
                "ssm_agent": True,
                "disk_size": 100,
                "min_size": 0,
                "max_size": 10,
                "instance_types": ["g4dn.xlarge"],
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

legacy_config = DominoCDKConfig(
    name='domino',
    aws_region='__FILL__',
    aws_account_id='__FILL__',
    tags={'domino-infrastructure': 'true'},
    install=Install(
        access_list=["0.0.0.0/0"],
        acm_cert_arn=None,
        hostname=None,
        registry_username=None,
        registry_password=None,
        istio_compatible=False,
        overrides={},
    ),
    vpc=VPC(
        id=None,
        create=True,
        cidr='10.0.0.0/16',
        public_cidr_mask=24,
        private_cidr_mask=24,
        availability_zones=[],
        max_azs=3,
        flow_logging=False,
        endpoints=True,
        bastion=VPC.Bastion(
            enabled=False, key_name=None, instance_type=None, ingress_ports=None, ami_id=None, user_data=None
        ),
    ),
    efs=EFS(
        backup=EFS.Backup(
            enable=True,
            schedule='0 12 * * ? *',
            move_to_cold_storage_after=35,
            delete_after=125,
            removal_policy='DESTROY',
        ),
        removal_policy_destroy=None,
    ),
    route53=Route53(zone_ids=[]),
    eks=EKS(
        version="1.19",
        private_api=True,
        max_nodegroup_azs=1,
        global_node_labels={'dominodatalab.com/domino-node': 'true'},
        global_node_tags={'k8s.io/cluster-autoscaler/node-template/label/dominodatalab.com/domino-node': 'true'},
        managed_nodegroups={},
        unmanaged_nodegroups={
            'platform-0': EKS.UnmanagedNodegroup(
                disk_size=100,
                key_name=None,
                min_size=1,
                max_size=10,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=['m5.2xlarge'],
                labels={'dominodatalab.com/node-pool': 'platform'},
                tags={'dominodatalab.com/node-pool': 'platform'},
                gpu=False,
                imdsv2_required=False,
                ssm_agent=True,
                taints={},
                spot=False,
            ),
            'compute-0': EKS.UnmanagedNodegroup(
                disk_size=100,
                key_name=None,
                min_size=1,
                max_size=10,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=['m5.2xlarge'],
                labels={'dominodatalab.com/node-pool': 'default', 'domino/build-node': 'true'},
                tags={'dominodatalab.com/node-pool': 'default', 'domino/build-node': 'true'},
                gpu=False,
                imdsv2_required=False,
                ssm_agent=True,
                taints={},
                spot=False,
            ),
            'gpu-0': EKS.UnmanagedNodegroup(
                disk_size=100,
                key_name=None,
                min_size=0,
                max_size=10,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=['g4dn.xlarge'],
                labels={'dominodatalab.com/node-pool': 'default-gpu', 'nvidia.com/gpu': 'true'},
                tags={'dominodatalab.com/node-pool': 'default-gpu'},
                gpu=True,
                imdsv2_required=False,
                ssm_agent=True,
                taints={'nvidia.com/gpu': 'true:NoSchedule'},
                spot=False,
            ),
        },
        secrets_encryption_key_arn=None,
    ),
    s3=S3(
        buckets=S3.BucketList(
            blobs=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            logs=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            backups=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            registry=S3.BucketList.Bucket(auto_delete_objects=False, removal_policy_destroy=False, sse_kms_key_id=None),
            monitoring=None,
        ),
    ),
    schema='0.0.2',
)


class TestConfig(unittest.TestCase):
    def test_default_template(self):
        c = config_template()
        self.assertEqual(c, default_config)

    def test_round_trip_template(self):
        c = config_template()
        d = config_loader(c.render())
        self.assertEqual(c, d)

    def test_legacy_template(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            c = config_loader(legacy_template)
            self.assertEqual(c, legacy_config)
            warn.assert_called_with(
                "Warning: Unused/unsupported config entries in config.vpc: {'bastion': {'enabled': False, 'instance_type': None, 'ingress_ports': None}}"
            )

        with patch("domino_cdk.config.util.log.warning") as warn:
            rendered_template = c.render()
            rendered_template["schema"] = "0.0.0"
            rendered_template["eks"]["nodegroups"] = rendered_template["eks"]["unmanaged_nodegroups"]
            del rendered_template["eks"]["unmanaged_nodegroups"]
            del rendered_template["vpc"]["bastion"]
            d = config_loader(rendered_template)
            warn.assert_not_called()
            self.assertEqual(c, d)

    def test_ingress_rule_loading(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            rules = [
                {"name": "some_rule", "from_port": 22, "to_port": 22, "protocol": "TCP", "ip_cidrs": ["10.0.0.0/16"]}
            ]
            loaded_rules = IngressRule.load_rules("some_name", rules)
            self.assertEqual(loaded_rules, [IngressRule("some_rule", 22, 22, "TCP", ["10.0.0.0/16"])])
            warn.assert_not_called()

    def test_ingress_rule_loading_extra_args(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            rules = [
                {
                    "name": "some_rule",
                    "from_port": 22,
                    "to_port": 22,
                    "protocol": "TCP",
                    "ip_cidrs": ["10.0.0.0/16"],
                    "extra": "boing",
                }
            ]
            loaded_rules = IngressRule.load_rules("some_name", rules)
            self.assertEqual(loaded_rules, [IngressRule("some_rule", 22, 22, "TCP", ["10.0.0.0/16"])])
            warn.assert_called_with("Warning: Unused/unsupported ingress rules in some_name: [{'extra': 'boing'}]")

    def test_ingress_rule_loading_none(self):
        loaded_rules = IngressRule.load_rules("some_name", None)
        self.assertEqual(loaded_rules, None)

    def test_managed_nodegroup_extra_args(self):
        test_group = {
            "disk_size": 20,
            "min_size": 1,
            "max_size": 1,
            "instance_types": ["t2.micro"],
            "labels": {},
            "tags": {},
            "spot": False,
            "desired_size": 1,
        }

        with patch("domino_cdk.config.util.log.warning") as warn:
            c = config_template().render()
            c["eks"]["managed_nodegroups"] = {"test_group": dict(test_group)}
            config_loader(dict(c))
            warn.assert_not_called()

        with patch("domino_cdk.config.util.log.warning") as warn:
            c = config_template().render()
            c["eks"]["managed_nodegroups"] = {"test_group": dict(test_group)}
            c["eks"]["managed_nodegroups"]["test_group"]["extra_arg"] = "boing"
            config_loader(dict(c))
            warn.assert_called_with(
                "Warning: Unused/unsupported managed nodegroup attribute in config.eks.unmanaged_nodegroups: ['extra_arg']"
            )
