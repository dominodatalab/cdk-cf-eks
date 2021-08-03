from typing import Any, Dict, Optional

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

    max_nodegroup_azs = 1 if dev_defaults else 3
    destroy_on_destroy = True if dev_defaults else False
    disk_size = 100 if dev_defaults else 1000
    platform_instance_type = "m5.4xlarge" if dev_defaults or istio_compatible else "m5.2xlarge"

    unmanaged_nodegroups = {}

    def add_nodegroups(name, count, min_size, instance_types, labels, disk_size=100, taints=None, gpu=False, tags=None):
        for i in range(0, count):
            unmanaged_nodegroups[f"{name}-{i}"] = EKS.UnmanagedNodegroup(
                gpu=gpu,
                imdsv2_required=True,
                ssm_agent=True,
                disk_size=disk_size,
                key_name=keypair_name,
                min_size=min_size,
                max_size=10,
                ami_id=None,
                user_data=None,
                instance_types=instance_types,
                labels=labels,
                tags=tags or {},
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
        tags={"k8s.io/cluster-autoscaler/node-template/resources/smarter-devices/fuse": "20"},
        disk_size=disk_size,
    )
    add_nodegroups(
        "gpu",
        gpu_nodegroups,
        0,
        ["p3.2xlarge"],
        {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
        taints={"nvidia.com/gpu": "true:NoSchedule"},
        tags={"k8s.io/cluster-autoscaler/node-template/resources/smarter-devices/fuse": "20"},
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
        max_azs=3,
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
        version="1.20",
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
        )
        if not disable_flow_logs
        else None,
    )

    overrides: Dict[Any, Any] = {}

    if istio_compatible:
        overrides = DominoCdkUtil.deep_merge(
            overrides,
            {
                "istio": {
                    "enabled": True,
                    "install": True,
                    "cni": False,
                },
                "services": {
                    "nginx_ingress": {
                        "chart_values": {
                            "controller": {
                                "config": {
                                    "use-proxy-protocol": "false",
                                    # AWS ELBs don't like nginx-ingress's default cipher suite--connections just hang w/ override
                                    "ssl-ciphers": "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA384:AES128-GCM-SHA256:AES128-SHA256:AES256-GCM-SHA384:AES256-SHA256:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!aECDH:!EDH-DSS-DES-CBC3-SHA:!EDH-RSA-DES-CBC3-SHA:!KRB5-DES-CBC3-SHA",  # noqa
                                    "ssl-protocols": "TLSv1.2 TLSv1.3",
                                },
                                "service": {
                                    "targetPorts": {"http": "http", "https": "https"},
                                    "annotations": {
                                        "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "ssl"
                                    },
                                },
                            }
                        }
                    }
                },
            },
        )

    if dev_defaults:
        overrides = DominoCdkUtil.deep_merge(
            overrides,
            {
                "services": {
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
