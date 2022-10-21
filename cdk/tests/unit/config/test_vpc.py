import unittest
from copy import deepcopy
from unittest.mock import patch

from domino_cdk.config import VPC, IngressRule

vpc_0_0_0_cfg = {"create": True, "id": None, "cidr": "10.0.0.0/24", "max_azs": 3}

vpc_0_0_1_cfg = {
    "create": True,
    "id": None,
    "cidr": "10.0.0.0/24",
    "public_cidr_mask": 27,
    "private_cidr_mask": 19,
    "max_azs": 3,
    "availability_zones": [],
}
vpc_0_0_1_cfg["bastion"] = {
    "enabled": False,
    "instance_type": None,
    "ingress_ports": None,
    "ami_id": None,
    "user_data": None,
}

bastion = {
    "enabled": True,
    "instance_type": "t2.micro",
    "ingress_ports": [
        {
            "name": "ssh",
            "from_port": 22,
            "to_port": 22,
            "protocol": "TCP",
            "ip_cidrs": ["0.0.0.0/0"],
        }
    ],
    "ami_id": "ami-1234abcd",
    "user_data": "some-user-data",
}

vpc_object = VPC(
    create=True,
    id=None,
    cidr="10.0.0.0/24",
    public_cidr_mask=27,
    private_cidr_mask=19,
    availability_zones=[],
    max_azs=3,
    flow_logging=False,
    endpoints=True,
    bastion=VPC.Bastion(
        enabled=False, key_name=None, instance_type=None, ingress_ports=None, ami_id=None, user_data=None
    ),
)

legacy_vpc_object = deepcopy(vpc_object)
legacy_vpc_object.public_cidr_mask = 24
legacy_vpc_object.private_cidr_mask = 24

bastion_object = VPC.Bastion(
    enabled=True,
    key_name=None,
    instance_type="t2.micro",
    ingress_ports=[IngressRule("ssh", 22, 22, "TCP", ["0.0.0.0/0"])],
    ami_id="ami-1234abcd",
    user_data="some-user-data",
)


class TestConfigVPC(unittest.TestCase):
    def test_from_0_0_0(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            vpc = VPC.from_0_0_0(deepcopy(vpc_0_0_0_cfg))
            warn.assert_not_called()
            self.assertEqual(vpc, legacy_vpc_object)

    def test_from_0_0_1(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            vpc = VPC.from_0_0_1(deepcopy(vpc_0_0_1_cfg))
            warn.assert_not_called()
            self.assertEqual(vpc, vpc_object)

    def test_from_0_0_1_wrong_schema(self):
        with self.assertRaisesRegex(KeyError, "bastion"):
            VPC.from_0_0_1(deepcopy(vpc_0_0_0_cfg))

    def test_oldest_newest_loaders_identical_result(self):
        new_vpc_cfg = deepcopy(vpc_0_0_1_cfg)
        new_vpc_cfg["public_cidr_mask"] = 24
        new_vpc_cfg["private_cidr_mask"] = 24
        vpc_old = VPC.from_0_0_0(deepcopy(vpc_0_0_0_cfg))
        vpc_new = VPC.from_0_0_1(new_vpc_cfg)
        self.assertEqual(vpc_old, vpc_new)

    def test_bastion(self):
        vpc_cfg = deepcopy(vpc_0_0_1_cfg)
        vpc_cfg["bastion"] = bastion
        vpc_obj_bastion = deepcopy(vpc_object)
        vpc_obj_bastion.bastion = deepcopy(bastion_object)
        with patch("domino_cdk.config.util.log.warning") as warn:
            VPC.from_0_0_1(vpc_cfg)
            warn.assert_not_called()

    def test_no_create_no_existing_vpc(self):
        vpc_cfg = deepcopy(vpc_0_0_1_cfg)
        vpc_cfg["create"] = False
        with self.assertRaisesRegex(ValueError, "Cannot provision into a VPC"):
            VPC.from_0_0_1(vpc_cfg)

    def test_too_few_azs(self):
        vpc_cfg = deepcopy(vpc_0_0_1_cfg)
        vpc_cfg["max_azs"] = 1
        with self.assertRaisesRegex(ValueError, "Must use at least two availability zones"):
            VPC.from_0_0_1(vpc_cfg)

    def test_bastion_user_data_no_ami(self):
        vpc_cfg = deepcopy(vpc_0_0_1_cfg)
        vpc_cfg["bastion"]["enabled"] = True
        vpc_cfg["bastion"]["ami_id"] = None
        vpc_cfg["bastion"]["user_data"] = "some-user-data"
        with self.assertRaisesRegex(ValueError, "Bastion instance with user_data requires an ami_id!"):
            VPC.from_0_0_1(vpc_cfg)
