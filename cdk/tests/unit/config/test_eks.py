import unittest
from copy import deepcopy
from unittest.mock import patch

from domino_cdk.config import EKS

eks_0_0_0_cfg = {
    "version": "1.19",
    "private_api": True,
    "max_nodegroup_azs": 1,
    "global_node_labels": {"dominodatalab.com/domino-node": "true"},
    "global_node_tags": {"k8s.io/cluster-autoscaler/node-template/label/dominodatalab.com/domino-node": "true"},
    "managed_nodegroups": {
        "compute": {
            "ssm_agent": True,
            "disk_size": 20,
            "min_size": 1,
            "max_size": 1,
            "instance_types": ["t2.micro"],
            "labels": {},
            "tags": {},
            "spot": False,
            "desired_size": 1,
        }
    },
    "nodegroups": {
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
        "nvidia": {
            "gpu": True,
            "ssm_agent": False,
            "disk_size": 100,
            "min_size": 0,
            "max_size": 10,
            "instance_types": ["p3.2xlarge"],
            "taints": {"nvidia.com/gpu": "true:NoSchedule"},
            "labels": {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
            "tags": {"dominodatalab.com/node-pool": "default-gpu"},
        },
    },
}

eks_0_0_1_cfg = deepcopy(eks_0_0_0_cfg)
eks_0_0_1_cfg["unmanaged_nodegroups"] = eks_0_0_1_cfg["nodegroups"]
del eks_0_0_1_cfg["nodegroups"]

managed_ngs = {
    "compute": EKS.ManagedNodegroup(
        ssm_agent=True,
        disk_size=20,
        key_name=None,
        min_size=1,
        max_size=1,
        ami_id=None,
        user_data=None,
        instance_types=["t2.micro"],
        labels={},
        tags={},
        spot=False,
        desired_size=1,
    )
}
unmanaged_ngs = {
    "platform": EKS.UnmanagedNodegroup(
        disk_size=100,
        key_name=None,
        min_size=1,
        max_size=10,
        ami_id=None,
        user_data=None,
        instance_types=["m5.2xlarge"],
        labels={"dominodatalab.com/node-pool": "platform"},
        tags={"dominodatalab.com/node-pool": "platform"},
        gpu=False,
        ssm_agent=True,
        taints={},
    ),
    "nvidia": EKS.UnmanagedNodegroup(
        disk_size=100,
        key_name=None,
        min_size=0,
        max_size=10,
        ami_id=None,
        user_data=None,
        instance_types=["p3.2xlarge"],
        labels={"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
        tags={"dominodatalab.com/node-pool": "default-gpu"},
        gpu=True,
        ssm_agent=False,
        taints={"nvidia.com/gpu": "true:NoSchedule"},
    ),
}

eks_object = EKS(
    version="1.19",
    private_api=True,
    max_nodegroup_azs=1,
    global_node_labels={"dominodatalab.com/domino-node": "true"},
    global_node_tags={"k8s.io/cluster-autoscaler/node-template/label/dominodatalab.com/domino-node": "true"},
    managed_nodegroups=managed_ngs,
    unmanaged_nodegroups=unmanaged_ngs,
    secrets_encryption_key_arn=None,
)


class TestConfigEKS(unittest.TestCase):
    def test_from_0_0_0(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            eks = EKS.from_0_0_0(deepcopy(eks_0_0_0_cfg))
            warn.assert_not_called()
            # The nodegroup tests are duplicative of the overall one,
            # but since they're the difference between the schemas
            # I wanted to focus on them specifically
            self.assertEqual(eks.managed_nodegroups, managed_ngs)
            self.assertEqual(eks.unmanaged_nodegroups, unmanaged_ngs)
            self.assertEqual(eks, eks_object)

    def test_from_0_0_1(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            eks = EKS.from_0_0_1(deepcopy(eks_0_0_1_cfg))
            warn.assert_not_called()
            # The nodegroup tests are duplicative of the overall one,
            # but since they're the difference between the schemas
            # I wanted to focus on them specifically
            self.assertEqual(eks.managed_nodegroups, managed_ngs)
            self.assertEqual(eks.unmanaged_nodegroups, unmanaged_ngs)
            self.assertEqual(eks, eks_object)

    def test_from_0_0_1_with_wrong_schema(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            eks = EKS.from_0_0_1(deepcopy(eks_0_0_0_cfg))
            warn.assert_called_with(
                f"Warning: Unused/unsupported config entries in config.eks: {{'nodegroups': {eks_0_0_0_cfg['nodegroups']}}}"
            )
            self.assertEqual(eks.managed_nodegroups, managed_ngs)

    def test_from_0_0_1_with_secrets_key(self):
        with patch("domino_cdk.config.eks.log.warning") as warn:
            eks_cfg = deepcopy(eks_0_0_1_cfg)
            eks_cfg["secrets_encryption_key_arn"] = "test_arn"
            eks = EKS.from_0_0_1(eks_cfg)
            warn.assert_not_called()
            self.assertEqual(eks.secrets_encryption_key_arn, "test_arn")

    def test_from_0_0_1_with_no_secrets_key(self):
        with patch("domino_cdk.config.eks.log.warning") as warn:
            eks_cfg = deepcopy(eks_0_0_1_cfg)
            eks = EKS.from_0_0_1(eks_cfg)
            warn.assert_not_called()
            self.assertIsNone(eks.secrets_encryption_key_arn)

    def test_oldest_newest_loaders_identical_result(self):
        eks_old = EKS.from_0_0_0(deepcopy(eks_0_0_0_cfg))
        eks_new = EKS.from_0_0_1(deepcopy(eks_0_0_1_cfg))
        self.assertEqual(eks_old, eks_new)

    def test_empty_nodegroups(self):
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        eks_cfg.pop("managed_nodegroups")
        eks_cfg.pop("unmanaged_nodegroups")
        eks = EKS.from_0_0_1(eks_cfg)
        eks_object_copy = deepcopy(eks_object)
        eks_object_copy.managed_nodegroups = {}
        eks_object_copy.unmanaged_nodegroups = {}
        self.assertEqual(eks, eks_object_copy)

    def test_ami_no_user_data(self):
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        eks_cfg["managed_nodegroups"]["compute"]["ami_id"] = "some-ami-id"
        eks_cfg["managed_nodegroups"]["compute"]["user_data"] = None
        eks_cfg["managed_nodegroups"]["compute"]["ssm_agent"] = None
        eks_cfg["managed_nodegroups"]["compute"]["labels"] = {}
        with self.assertRaisesRegex(
            ValueError, "Managed nodegroup \\[compute\\]: User data must be provided when specifying a custom AMI"
        ):
            EKS.from_0_0_1(eks_cfg)

    def test_ami_incompatible_options(self):
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        eks_cfg["managed_nodegroups"]["compute"]["ami_id"] = "some-ami-id"
        eks_cfg["managed_nodegroups"]["compute"]["user_data"] = "some-user-data"
        eks_cfg["managed_nodegroups"]["compute"]["ssm_agent"] = True
        eks_cfg["managed_nodegroups"]["compute"]["labels"] = {}
        with self.assertRaisesRegex(ValueError, "Managed nodegroup \\[compute\\]: ssm_agent, labels and taints"):
            EKS.from_0_0_1(eks_cfg)

    def test_ami_unmanaged_multiple_exceptions(self):
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        eks_cfg["unmanaged_nodegroups"]["platform"]["ami_id"] = "some-ami-id"
        eks_cfg["unmanaged_nodegroups"]["platform"]["user_data"] = None
        with self.assertRaisesRegex(
            ValueError,
            "Unmanaged nodegroup \\[platform\\]: User data must be provided.*Unmanaged nodegroup \\[platform\\]: ssm_agent, labels and taints",
        ):
            EKS.from_0_0_1(eks_cfg)

    def test_key_name(self):
        key_name = "abcd1234-key-pair"
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        eks_cfg["managed_nodegroups"]["compute"]["key_name"] = key_name
        eks_cfg["unmanaged_nodegroups"]["platform"]["key_name"] = key_name
        eks = EKS.from_0_0_1(eks_cfg)
        self.assertEqual(eks.managed_nodegroups["compute"].key_name, key_name)
        self.assertEqual(eks.unmanaged_nodegroups["platform"].key_name, key_name)

    def test_no_key_pair(self):
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        # Current default config has this as a no-op, but worthwhile testing in case that changes and we overlook
        eks_cfg["managed_nodegroups"]["compute"].pop("key_name", None)
        eks_cfg["unmanaged_nodegroups"]["platform"].pop("key_name", None)
        eks = EKS.from_0_0_1(eks_cfg)
        self.assertEqual(eks.managed_nodegroups["compute"].key_name, None)
        self.assertEqual(eks.unmanaged_nodegroups["platform"].key_name, None)

    def test_min_size_zero(self):
        eks_cfg = deepcopy(eks_0_0_1_cfg)
        eks_cfg["managed_nodegroups"]["compute"]["min_size"] = 0
        with self.assertRaisesRegex(ValueError, "Managed nodegroup \\[compute\\] has min_size of 0."):
            EKS.from_0_0_1(eks_cfg)

    def test_managed_nodegroup(self):
        test_group_cfg = deepcopy(eks_0_0_1_cfg["managed_nodegroups"]["compute"])

        with patch("domino_cdk.config.util.log.warning") as warn:
            ng = EKS.ManagedNodegroup.load(test_group_cfg)
            warn.assert_not_called()
            self.assertEqual(ng, managed_ngs["compute"])

    def test_managed_nodegroup_extra_args(self):
        test_group_cfg = deepcopy(eks_0_0_1_cfg["managed_nodegroups"]["compute"])
        test_group_cfg["extra_arg"] = "boing"

        with patch("domino_cdk.config.util.log.warning") as warn:
            ng = EKS.ManagedNodegroup.load(test_group_cfg)
            self.assertEqual(ng, managed_ngs["compute"])
            warn.assert_called_with(
                "Warning: Unused/unsupported managed nodegroup attribute in config.eks.unmanaged_nodegroups: ['extra_arg']"
            )

    def test_unmanaged_nodegroup(self):
        test_group_cfg = deepcopy(eks_0_0_1_cfg["unmanaged_nodegroups"]["platform"])

        with patch("domino_cdk.config.util.log.warning") as warn:
            ng = EKS.UnmanagedNodegroup.load(test_group_cfg)
            warn.assert_not_called()
            self.assertEqual(ng, unmanaged_ngs["platform"])

    def test_unmanaged_nodegroup_extra_args(self):
        test_group_cfg = deepcopy(eks_0_0_1_cfg["unmanaged_nodegroups"]["platform"])
        test_group_cfg["extra_arg"] = "boing"

        with patch("domino_cdk.config.util.log.warning") as warn:
            ng = EKS.UnmanagedNodegroup.load(test_group_cfg)
            self.assertEqual(ng, unmanaged_ngs["platform"])
            warn.assert_called_with(
                "Warning: Unused/unsupported unmanaged nodegroup attribute in config.eks.unmanaged_nodegroups: ['extra_arg']"
            )

    def test_nodegroup_base(self):
        test_group_cfg = deepcopy(eks_0_0_1_cfg["managed_nodegroups"]["compute"])
        test_group_cfg["key_name"] = None
        test_group_cfg["ami_id"] = "ami-1234"
        test_group_cfg["user_data"] = "some-user-data"

        expected_base_result = deepcopy(test_group_cfg)
        del expected_base_result["spot"]
        del expected_base_result["desired_size"]
        expected_base_result["ami_id"] = "ami-1234"
        expected_base_result["user_data"] = "some-user-data"

        base_ng_dict = EKS.NodegroupBase.base_load(test_group_cfg)
        self.assertEqual(base_ng_dict, expected_base_result)
        self.assertEqual(test_group_cfg, {"spot": False, "desired_size": 1})
