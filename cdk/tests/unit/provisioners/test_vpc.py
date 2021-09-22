import aws_cdk.aws_s3 as s3
from aws_cdk.assertions import Template
from aws_cdk.core import App, Environment, Stack

from domino_cdk.config import VPC, IngressRule
from domino_cdk.provisioners.vpc import DominoVpcProvisioner

from . import TestCase


class TestDominoVPCProvisioner(TestCase):
    def setUp(self):
        self.app = App()
        self.stack = Stack(self.app, "VPC", env=Environment(region="us-west-2", account="1234567890"))

    def test_vpc(self):
        vpc_config = VPC(
            id=None,
            create=True,
            cidr="10.0.0.0/16",
            public_cidr_mask=27,
            private_cidr_mask=19,
            availability_zones=[],
            max_azs=3,
            flow_logging=False,
            bastion=VPC.Bastion(
                enabled=True,
                key_name="domino-test",
                instance_type="t2.micro",
                ingress_ports=[
                    IngressRule(name="ssh", from_port=22, to_port=22, protocol="TCP", ip_cidrs=["0.0.0.0/0"])
                ],
                ami_id=None,
                user_data=None,
            ),
        )

        DominoVpcProvisioner(self.stack, "construct-1", "test-vpc", vpc_config, False, None)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("AWS::EC2::VPC", 1)
        assertion.resource_count_is("AWS::EC2::Subnet", 9)
        assertion.resource_count_is("AWS::EC2::InternetGateway", 1)
        assertion.resource_count_is("AWS::EC2::NatGateway", 3)
        assertion.resource_count_is("AWS::EC2::RouteTable", 9)
        assertion.resource_count_is("AWS::EC2::Instance", 1)

        template = self.app.synth().get_stack("VPC").template
        instance = self.find_resource(template, "AWS::EC2::Instance")
        self.assertEqual(
            [
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {"DeleteOnTermination": True, "Encrypted": True, "VolumeSize": 40, "VolumeType": "gp3"},
                }
            ],
            instance["Properties"].get("BlockDeviceMappings"),
        )

    def test_flow_logging_enabled_no_bucket(self):
        vpc_config = VPC(
            id=None,
            create=True,
            cidr="10.0.0.0/16",
            public_cidr_mask=27,
            private_cidr_mask=19,
            availability_zones=[],
            max_azs=3,
            flow_logging=True,
            bastion=VPC.Bastion(
                enabled=False,
                key_name="",
                instance_type="",
                ingress_ports=[],
                ami_id=None,
                user_data=None,
            ),
        )

        with self.assertRaisesRegex(ValueError, "VPC flow logging enabled without"):
            DominoVpcProvisioner(self.stack, "construct-1", "test-vpc", vpc_config, False, None)

    def test_vpc_flow_logging(self):
        vpc_config = VPC(
            id=None,
            create=True,
            cidr="10.0.0.0/16",
            public_cidr_mask=27,
            private_cidr_mask=19,
            availability_zones=[],
            max_azs=3,
            flow_logging=True,
            bastion=VPC.Bastion(
                enabled=False,
                key_name="",
                instance_type="",
                ingress_ports=[],
                ami_id=None,
                user_data=None,
            ),
        )

        logging_bucket = s3.Bucket(self.stack, "logging-bucket")
        DominoVpcProvisioner(self.stack, "construct-1", "test-vpc", vpc_config, False, logging_bucket)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("AWS::EC2::FlowLog", 1)

    def test_bring_your_own_vpc(self):
        vpc_config = VPC(
            id="vpc-123456",
            create=False,
            cidr="10.0.0.0/16",
            public_cidr_mask=27,
            private_cidr_mask=19,
            availability_zones=[],
            max_azs=3,
            flow_logging=False,
            bastion=VPC.Bastion(
                enabled=False,
                key_name="",
                instance_type="",
                ingress_ports=[],
                ami_id=None,
                user_data=None,
            ),
        )

        DominoVpcProvisioner(self.stack, "construct-1", "test-vpc", vpc_config, False, None)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("AWS::EC2::VPC", 0)

    def test_bastion_bring_your_own_ami(self):
        vpc_config = VPC(
            id=None,
            create=True,
            cidr="10.0.0.0/16",
            public_cidr_mask=27,
            private_cidr_mask=19,
            availability_zones=[],
            max_azs=3,
            flow_logging=False,
            bastion=VPC.Bastion(
                enabled=True,
                key_name="domino-test",
                instance_type="t2.micro",
                ami_id="ami-1234567890",
                ingress_ports=[
                    IngressRule(name="ssh", from_port=22, to_port=22, protocol="TCP", ip_cidrs=["0.0.0.0/0"])
                ],
                user_data=None,
            ),
        )

        DominoVpcProvisioner(self.stack, "construct-1", "test-vpc", vpc_config, False, None)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("AWS::EC2::Instance", 1)

        template = self.app.synth().get_stack("VPC").template
        instance = self.find_resource(template, "AWS::EC2::Instance")
        self.assertIsNone(instance["Properties"].get("BlockDeviceMappings"))
        self.assertEqual("ami-1234567890", instance["Properties"]["ImageId"])
