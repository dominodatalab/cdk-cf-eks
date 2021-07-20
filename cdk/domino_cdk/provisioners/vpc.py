from typing import Optional

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk.aws_s3 as s3
import aws_cdk.custom_resources as cr
from aws_cdk import core as cdk

from domino_cdk import config

from .ami import root_device_mapping

_DominoVpcStack = None


class DominoVpcProvisioner:
    def __init__(
        self,
        parent: cdk.Construct,
        construct_id: str,
        name: str,
        vpc: config.VPC,
        nest: bool,
        monitoring_bucket: Optional[s3.Bucket],
        **kwargs,
    ) -> None:
        self.parent = parent
        self.scope = cdk.NestedStack(self.parent, construct_id, **kwargs) if nest else self.parent

        self._availability_zones = vpc.availability_zones

        self.provision_vpc(name, vpc, monitoring_bucket)
        self.bastion_sg = self.provision_bastion(name, vpc.bastion)

    def provision_vpc(self, stack_name: str, vpc: config.VPC, monitoring_bucket: Optional[s3.Bucket]):
        self.public_subnet_name = f"{stack_name}-public"
        self.private_subnet_name = f"{stack_name}-private"
        if not vpc.create:
            self.vpc = ec2.Vpc.from_lookup(self.scope, vpc.id)
            return

        nat_provider = ec2.NatProvider.gateway()
        self.vpc = ec2.Vpc(
            self.scope,
            "VPC",
            max_azs=vpc.max_azs,
            cidr=vpc.cidr,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name=self.public_subnet_name,
                    cidr_mask=24,  # can't use token ids
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE,
                    name=self.private_subnet_name,
                    cidr_mask=24,  # can't use token ids
                ),
            ],
            gateway_endpoints={
                "S3": ec2.GatewayVpcEndpointOptions(service=ec2.GatewayVpcEndpointAwsService.S3),
            },
            nat_gateway_provider=nat_provider,
        )
        cdk.Tags.of(self.vpc).add("Name", stack_name)
        cdk.CfnOutput(self.parent, "vpc-output", value=self.vpc.vpc_cidr_block)

        default_sg = ec2.SecurityGroup.from_security_group_id(
            self.scope, "default_security_group", self.vpc.vpc_default_security_group
        )
        # TODO: Default security group isn't tagged, and using cdk.Tags.of doesn't seem to work here

        cr.AwsCustomResource(
            self.scope,
            "RevokeDefaultSecurityGroupEgress",
            log_retention=logs.RetentionDays.ONE_DAY,
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_create=cr.AwsSdkCall(
                action="revokeSecurityGroupEgress",
                service="EC2",
                parameters={
                    "GroupId": default_sg.security_group_id,
                    "IpPermissions": [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
                },
                physical_resource_id=cr.PhysicalResourceId.of("RevokeDefaultSecurityGroupEgress"),
            ),
        )

        cr.AwsCustomResource(
            self.scope,
            "RevokeDefaultSecurityGroupIngress",
            log_retention=logs.RetentionDays.ONE_DAY,
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_create=cr.AwsSdkCall(
                action="revokeSecurityGroupIngress",
                service="EC2",
                parameters={
                    "GroupId": default_sg.security_group_id,
                    "IpPermissions": [
                        {"IpProtocol": "-1", "UserIdGroupPairs": [{"GroupId": default_sg.security_group_id}]}
                    ],
                },
                physical_resource_id=cr.PhysicalResourceId.of("RevokeDefaultSecurityGroupIngress"),
            ),
        )

        # ripped off this: https://github.com/aws/aws-cdk/issues/9573
        pod_cidr = ec2.CfnVPCCidrBlock(self.scope, "PodCidr", vpc_id=self.vpc.vpc_id, cidr_block="100.64.0.0/16")
        c = 0
        for az in self.vpc.availability_zones:
            pod_subnet = ec2.PrivateSubnet(
                self.scope,
                # this can't be okay
                f"{stack_name}-pod-{c}",  # Can't use parameter/token in this name
                vpc_id=self.vpc.vpc_id,
                availability_zone=az,
                cidr_block=f"100.64.{c}.0/18",
            )

            pod_subnet.add_default_nat_route(
                [gw for gw in nat_provider.configured_gateways if gw.az == az][0].gateway_id
            )
            pod_subnet.node.add_dependency(pod_cidr)
            # TODO: need to tag

            c += 64

        for endpoint in [
            "ec2",  # Only these first three have predefined consts
            "sts",
            "ecr.api",
            "autoscaling",
            "ecr.dkr",
        ]:  # TODO: Do we need an s3 interface as well? or just the gateway?
            self.vpc_endpoint = ec2.InterfaceVpcEndpoint(
                self.scope,
                f"{endpoint}-ENDPOINT",
                vpc=self.vpc,
                service=ec2.InterfaceVpcEndpointAwsService(endpoint, port=443),
                # private_dns_enabled=True,
                subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE),
            )

        # TODO until https://github.com/aws/aws-cdk/issues/14194
        for idx, subnet_id in enumerate(self.vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnet_ids):
            name = f"DisableMapPublicIpLaunch-{idx}"
            cr.AwsCustomResource(
                self.scope,
                name,
                log_retention=logs.RetentionDays.ONE_DAY,
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
                on_create=cr.AwsSdkCall(
                    action="modifySubnetAttribute",
                    service="EC2",
                    parameters={"MapPublicIpOnLaunch": {"Value": False}, "SubnetId": subnet_id},
                    physical_resource_id=cr.PhysicalResourceId.of(name),
                ),
            )

        if vpc.flow_logging:
            if not monitoring_bucket:
                raise ValueError(
                    "VPC flow logging enabled without a corresponding S3 bucket destination. Ensure the `monitoring_bucket` is configured correctly."
                )

            self.vpc.add_flow_log(
                "rejectFlowLogs",
                destination=ec2.FlowLogDestination.to_s3(monitoring_bucket),
                traffic_type=ec2.FlowLogTrafficType.REJECT,
            )

    def provision_bastion(self, name: str, bastion: config.VPC.Bastion) -> Optional[ec2.SecurityGroup]:
        if not bastion.enabled:
            return None

        root_device_name = "/dev/xvda"  # This only works for AL2
        if bastion.ami_id:
            region = cdk.Stack.of(self.scope).region
            machine_image = ec2.MachineImage.generic_linux(
                {region: bastion.ami_id},
                user_data=ec2.UserData.custom(bastion.user_data) if bastion.user_data else None,
            )

            root_device_name = root_device_mapping(self.scope, bastion.ami_id).name
        else:
            machine_image = ec2.GenericSSMParameterImage(
                "/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2", ec2.OperatingSystemType.LINUX
            )

        bastion_sg = ec2.SecurityGroup(
            self.scope,
            "bastion_sg",
            vpc=self.vpc,
            security_group_name=f"{name}-bastion",
        )

        for rule in bastion.ingress_ports:
            for ip_cidr in rule.ip_cidrs:
                bastion_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_cidr),
                    connection=ec2.Port(
                        protocol=ec2.Protocol(rule.protocol),
                        string_representation=rule.name,
                        from_port=rule.from_port,
                        to_port=rule.to_port,
                    ),
                )

        bastion_instance = ec2.Instance(
            self.scope,
            "bastion",
            machine_image=machine_image,
            vpc=self.vpc,
            instance_type=ec2.InstanceType(bastion.instance_type),
            block_devices=[
                ec2.BlockDevice(
                    device_name=root_device_name,
                    volume=ec2.BlockDeviceVolume.ebs(
                        40,  # TODO: this requires the AMI volume be <= 40GiB already
                        delete_on_termination=True,
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP2,
                    ),
                )
            ],
            role=None,
            key_name=bastion.key_name,
            security_group=bastion_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_group_name=self.public_subnet_name,
            ),
        )

        ec2.CfnEIP(
            self.scope,
            "bastion_eip",
            instance_id=bastion_instance.instance_id,
        )

        cr.AwsCustomResource(
            self.scope,
            "DisableBastionHTTPEndpoint",
            log_retention=logs.RetentionDays.ONE_DAY,
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_update=cr.AwsSdkCall(
                action="modifyInstanceMetadataOptions",
                service="EC2",
                parameters={
                    "InstanceId": bastion_instance.instance_id,
                    "HttpEndpoint": "disabled",
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"DisableBastionHTTPEndpoint-{bastion_instance.instance_id}"
                ),
            ),
        )

        cdk.CfnOutput(self.parent, "bastion_public_ip", value=bastion_instance.instance_public_ip)

        return bastion_sg

    # Override default max of 2 AZs, as well as allow configurability
    @property
    def availability_zones(self):
        return self._availability_zones or [
            cdk.Fn.select(0, cdk.Fn.get_azs(self.scope.region)),
            cdk.Fn.select(1, cdk.Fn.get_azs(self.scope.region)),
            cdk.Fn.select(2, cdk.Fn.get_azs(self.scope.region)),
        ]
