from domino_cdk import __version__
from domino_cdk.config import EFS, EKS, S3, VPC, DominoCDKConfig, IngressRule, Route53


def config_template(
    name: str = "domino",
    platform_nodegroups: int = 1,
    compute_nodegroups: int = 1,
    gpu_nodegroups: int = 1,
    keypair_name: str = None,
    bastion: bool = False,
    private_api: bool = False,
    dev_defaults: bool = False,
):
    fill = "__FILL__"

    max_nodegroup_azs = 3
    destroy_on_destroy = False
    disk_size = 1000
    platform_instance_type = "m5.2xlarge"
    platform_min_size = 3
    if dev_defaults:
        max_nodegroup_azs = 1
        destroy_on_destroy = True
        disk_size = 100
        platform_instance_type = "m5.4xlarge"
        platform_min_size = 1

    unmanaged_nodegroups = {}

    def add_nodegroups(name, count, min_size, instance_types, labels, disk_size=disk_size, taints=None, gpu=False):
        for i in range(0, count):
            unmanaged_nodegroups[f"{name}-{i}"] = EKS.UnmanagedNodegroup(
                gpu=gpu,
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
            )

    add_nodegroups(
        "platform",
        platform_nodegroups,
        platform_min_size,
        [platform_instance_type],
        {"dominodatalab.com/node-pool": "platform"},
    )
    add_nodegroups(
        "compute",
        compute_nodegroups,
        1,
        ["m5.2xlarge"],
        {"dominodatalab.com/node-pool": "default", "domino/build-node": "true"},
    )
    add_nodegroups(
        "gpu",
        gpu_nodegroups,
        0,
        ["p3.2xlarge"],
        {"dominodatalab.com/node-pool": "default-gpu", "nvidia.com/gpu": "true"},
        taints={"nvidia.com/gpu": "true:NoSchedule"},
        gpu=True,
    )

    vpc = VPC(
        id=None,
        create=True,
        cidr='10.0.0.0/16',
        availability_zones=[],
        max_azs=3,
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
        version="1.19",
        private_api=private_api,
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
        }
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
        install=install,
        vpc=vpc,
        efs=efs,
        route53=route53,
        eks=eks,
        s3=s3,
        schema=__version__,
    )
