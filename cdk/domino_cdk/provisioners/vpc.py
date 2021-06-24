import aws_cdk.aws_ec2 as ec2
from aws_cdk import core as cdk

from domino_cdk import config

_DominoVpcStack = None


class DominoVpcProvisioner:
    def __init__(
        self, parent: cdk.Construct, construct_id: str, name: str, vpc: config.VPC, nest: bool, **kwargs
    ) -> None:
        self.parent = parent
        self.scope = cdk.NestedStack(self.parent, construct_id, **kwargs) if nest else self.parent

        self._availability_zones = vpc.availability_zones

        self.provision_vpc(name, vpc)
        self.bastion_sg = self.provision_bastion(name, vpc.bastion)

    def provision_vpc(self, name: str, vpc: config.VPC):
        self.public_subnet_name = f"{name}-public"
        self.private_subnet_name = f"{name}-private"
        if not vpc.create:
            self.vpc = ec2.Vpc.from_lookup("Vpc", vpc_id=vpc.id)
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
        cdk.Tags.of(self.vpc).add("Name", name)
        cdk.CfnOutput(self.parent, "vpc-output", value=self.vpc.vpc_cidr_block)

        default_sg = ec2.SecurityGroup.from_security_group_id(
            self.scope, "default_security_group", self.vpc.vpc_default_security_group, allow_all_outbound=False
        )
        # TODO: Default security group isn't tagged, and using cdk.Tags.of doesn't seem to work here

        # Disabling default ingress/egress
        default_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4("127.0.0.1/32"),
            connection=ec2.Port(
                protocol=ec2.Protocol("ALL"),
                string_representation="Default Outbound",
                from_port=0,
                to_port=65535,
            ),
        )
        default_sg.add_egress_rule(
            peer=ec2.Peer.ipv4("127.0.0.1/32"),
            connection=ec2.Port(
                protocol=ec2.Protocol("ALL"),
                string_representation="Default Outbound",
                from_port=0,
                to_port=65535,
            ),
        )

        # ripped off this: https://github.com/aws/aws-cdk/issues/9573
        pod_cidr = ec2.CfnVPCCidrBlock(self.scope, "PodCidr", vpc_id=self.vpc.vpc_id, cidr_block="100.64.0.0/16")
        c = 0
        for az in self.vpc.availability_zones:
            pod_subnet = ec2.PrivateSubnet(
                self.scope,
                # this can't be okay
                f"{name}-pod-{c}",  # Can't use parameter/token in this name
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

    def provision_bastion(self, name: str, bastion: config.VPC.Bastion) -> None:
        if not bastion.enabled:
            return None
        if bastion.ami_id:
            machine_image = ec2.MachineImage.generic_linux(
                {self.region: bastion.ami_id},
                user_data=ec2.UserData.custom(bastion.user_data),
            )
        else:
            if not self.scope.account.isnumeric():  # TODO: Can we get rid of this requirement?
                raise ValueError(
                    "Error loooking up AMI: Must provide explicit AWS account ID to do AMI lookup. Either provide AMI ID or AWS account id"
                )

            machine_image = ec2.LookupMachineImage(
                name="ubuntu/images/hvm-ssd/ubuntu-bionic-18.04-amd64-server-*", owners=["099720109477"]
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

        bastion = ec2.Instance(
            self.scope,
            "bastion",
            machine_image=machine_image,
            vpc=self.vpc,
            instance_type=ec2.InstanceType(bastion.instance_type),
            key_name=bastion.key_name,
            security_group=bastion_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_group_name=self.public_subnet_name,
            ),
        )

        ec2.CfnEIP(
            self.scope,
            "bastion_eip",
            instance_id=bastion.instance_id,
        )

        cdk.CfnOutput(self.parent, "bastion_public_ip", value=bastion.instance_public_ip)

        return bastion_sg

    # Override default max of 2 AZs, as well as allow configurability
    @property
    def availability_zones(self):
        return self._availability_zones or [
            cdk.Fn.select(0, cdk.Fn.get_azs(self.scope.region)),
            cdk.Fn.select(1, cdk.Fn.get_azs(self.scope.region)),
            cdk.Fn.select(2, cdk.Fn.get_azs(self.scope.region)),
        ]
