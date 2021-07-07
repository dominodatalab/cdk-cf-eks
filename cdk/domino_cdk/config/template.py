from typing import Optional

from domino_cdk import __version__
from domino_cdk.config import EFS, EKS, S3, VPC, DominoCDKConfig, IngressRule, Route53


def config_template(
    name: str = "domino",
    platform_nodegroups: int = 1,
    compute_nodegroups: int = 1,
    gpu_nodegroups: int = 1,
    keypair_name: str = None,
    secrets_encryption_key_arn: Optional[str] = None,
    bastion: bool = False,
    private_api: bool = False,
    dev_defaults: bool = False,
):
    fill = "__FILL__"

    max_nodegroup_azs = 3
    destroy_on_destroy = False
    disk_size = 1000
    platform_instance_type = "m5.2xlarge"
    if dev_defaults:
        max_nodegroup_azs = 1
        destroy_on_destroy = True
        disk_size = 100
        platform_instance_type = "m5.4xlarge"

    unmanaged_nodegroups = {}

    def add_nodegroups(name, count, min_size, instance_types, labels, disk_size=100, taints=None, gpu=False):
        for i in range(0, count):
            unmanaged_nodegroups[f"{name}-{i}"] = EKS.UnmanagedNodegroup(
                gpu=gpu,
                imdsv2_required=False,
                ssm_agent=True,
                disk_size=disk_size,
                key_name=keypair_name,
                min_size=min_size,
                max_size=10,
                ami_id=None,
                user_data=None,
                instance_types=instance_types,
                labels=labels,
                tags={},
                taints=taints or {},
                ingress_ports=None,
            )

    add_nodegroups(
        "platform",
        platform_nodegroups,
        1,
        [platform_instance_type],
        {"dominodatalab.com/node-pool": "platform"},
    )
    add_nodegroups(
        "compute",
        compute_nodegroups,
        0,
        ["m5.2xlarge"],
        {"dominodatalab.com/node-pool": "default"},
        disk_size=disk_size,
    )
    add_nodegroups(
        "gpu",
        gpu_nodegroups,
        0,
        ["p3.2xlarge"],
        {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
        taints={"nvidia.com/gpu": "true:NoSchedule"},
        gpu=True,
        disk_size=disk_size,
    )

    vpc = VPC(
        id=None,
        create=True,
        cidr='10.0.0.0/16',
        availability_zones=[],
        max_azs=3,
        flow_logging=True,
        bastion=VPC.Bastion(
            enabled=bastion,
            key_name=keypair_name,
            instance_type='t2.micro',
            ingress_ports=[IngressRule(name='ssh', from_port=22, to_port=22, protocol='TCP', ip_cidrs=['0.0.0.0/0'])],
            ami_id=None,
            user_data=None,
        ),
    )

    efs = EFS(
        backup=EFS.Backup(
            enable=True,
            schedule='0 12 * * ? *',
            move_to_cold_storage_after=35,
            delete_after=125,
            removal_policy="DESTROY" if destroy_on_destroy else False,
        ),
        removal_policy_destroy=destroy_on_destroy,
    )

    eks = EKS(
        version="1.20",
        control_plane_access_cidrs=None,
        private_api=private_api,
        secrets_encryption_key_arn=secrets_encryption_key_arn,
        max_nodegroup_azs=max_nodegroup_azs,
        global_node_labels={'dominodatalab.com/domino-node': 'true'},
        global_node_tags={},
        managed_nodegroups={},
        unmanaged_nodegroups=unmanaged_nodegroups,
    )

    route53 = Route53(zone_ids=[])

    s3 = S3(
        buckets={
            'blobs': S3.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            'logs': S3.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            'backups': S3.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            'registry': S3.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
        },
        monitoring_bucket=S3.Bucket(
            auto_delete_objects=destroy_on_destroy,
            removal_policy_destroy=destroy_on_destroy,
            sse_kms_key_id=None,
        ),
    )

    install = {}

    if dev_defaults:
        install["services"] = {
            "nucleus": {
                "chart_values": {
                    "replicaCount": {
                        "dispatcher": 1,
                        "frontend": 1,
                    },
                    "keycloak": {
                        "createIntegrationTestUser": True,
                    },
                },
            },
        }

    return DominoCDKConfig(
        name=name,
        aws_region=fill,
        aws_account_id=fill,
        tags={"domino-infrastructure": "true"},
        create_iam_roles_for_service_accounts=False,
        install=install,
        vpc=vpc,
        efs=efs,
        route53=route53,
        eks=eks,
        s3=s3,
        schema=__version__,
    )
