from typing import Any, Dict, List, Optional

from domino_cdk import __version__
from domino_cdk.config import (
    EFS,
    EKS,
    S3,
    VPC,
    DominoCDKConfig,
    IngressRule,
    Install,
    Route53,
)
from domino_cdk.util import DominoCdkUtil


def config_template(
    name: str = "domino",
    aws_region: str = None,
    aws_account_id: str = None,
    platform_nodegroups: int = 1,
    compute_nodegroups: int = 1,
    gpu_nodegroups: int = 1,
    keypair_name: str = None,
    secrets_encryption_key_arn: Optional[str] = None,
    bastion: bool = False,
    private_api: bool = False,
    dev_defaults: bool = False,
    istio_compatible: bool = False,
    registry_username: str = None,
    registry_password: str = None,
    acm_cert_arn: str = None,
    hostname: str = None,
    disable_flow_logs: bool = False,
):
    fill = "__FILL__"

    destroy_on_destroy = dev_defaults
    disk_size = 100 if dev_defaults else 1000
    platform_instance_type = "m5.4xlarge" if istio_compatible else "m5.2xlarge"

    unmanaged_nodegroups = {}

    def add_nodegroups(
        name: str,
        count: int,
        min_size: int,
        instance_types: List[str],
        labels: Dict,
        disk_size: int = 100,
        taints: Optional[Dict] = None,
        gpu: bool = False,
        max_size: int = 10,
    ):
        for i in range(0, count):
            unmanaged_nodegroups[f"{name}-{i}"] = EKS.UnmanagedNodegroup(
                gpu=gpu,
                imdsv2_required=True,
                ssm_agent=True,
                disk_size=disk_size,
                key_name=keypair_name,
                min_size=min_size,
                max_size=max_size,
                availability_zones=None,
                ami_id=None,
                user_data=None,
                instance_types=instance_types,
                labels=labels,
                tags={},
                taints=taints or {},
                spot=False,
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
        max_size=30 if dev_defaults else 10,
    )
    add_nodegroups(
        "gpu",
        gpu_nodegroups,
        0,
        ["g4dn.xlarge"] if dev_defaults else ["p3.2xlarge"],
        {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
        taints={"nvidia.com/gpu": "true:NoSchedule"},
        gpu=True,
        disk_size=disk_size,
    )

    vpc = VPC(
        id=None,
        create=True,
        cidr='10.0.0.0/16',
        public_cidr_mask=27,
        private_cidr_mask=19,
        availability_zones=[],
        max_azs=2 if dev_defaults else 3,
        flow_logging=not disable_flow_logs,
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
        version="1.21",
        private_api=private_api,
        secrets_encryption_key_arn=secrets_encryption_key_arn,
        max_nodegroup_azs=3,
        global_node_labels={'dominodatalab.com/domino-node': 'true'},
        global_node_tags={},
        managed_nodegroups={},
        unmanaged_nodegroups=unmanaged_nodegroups,
    )

    route53 = Route53(zone_ids=[])

    s3 = S3(
        buckets=S3.BucketList(
            blobs=S3.BucketList.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            logs=S3.BucketList.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            backups=S3.BucketList.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            registry=S3.BucketList.Bucket(
                auto_delete_objects=destroy_on_destroy, removal_policy_destroy=destroy_on_destroy, sse_kms_key_id=None
            ),
            monitoring=S3.BucketList.Bucket(
                auto_delete_objects=destroy_on_destroy,
                removal_policy_destroy=destroy_on_destroy,
                sse_kms_key_id=None,
            )
            if not disable_flow_logs
            else None,
        )
    )

    overrides: Dict[Any, Any] = {}

    if dev_defaults:
        overrides = DominoCdkUtil.deep_merge(
            overrides,
            {
                "release_overrides": {
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
                    }
                }
            },
        )

    install = Install(
        access_list=["0.0.0.0/0"],
        acm_cert_arn=acm_cert_arn,
        hostname=hostname,
        registry_username=registry_username,
        registry_password=registry_password,
        istio_compatible=istio_compatible,
        overrides=overrides,
    )

    return DominoCDKConfig(
        name=name,
        aws_region=aws_region or fill,
        aws_account_id=aws_account_id or fill,
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
