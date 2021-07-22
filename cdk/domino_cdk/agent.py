from typing import Any, Dict, Optional

from aws_cdk.aws_s3 import Bucket

from domino_cdk.config import Install


def generate_install_config(
    name: str,
    install: Install,
    aws_region: str,
    eks_cluster_name: str,
    pod_cidr: str,
    global_node_selectors: Dict[str, str],
    buckets: Dict[str, Bucket],
    monitoring_bucket: Optional[Bucket],
    efs_fs_ap_id: str,
    r53_zone_ids: str,
    r53_owner_id: str,
) -> Dict:
    agent_cfg: Dict[str, Any] = {
        "name": name,
        "hostname": "__FILL__",
        "pod_cidr": pod_cidr,
        "global_node_selectors": global_node_selectors,
        "storage_classes": {
            "shared": {
                "efs": {
                    "region": aws_region,
                    "filesystem_id": efs_fs_ap_id,
                }
            },
        },
        "blob_storage": {
            "projects": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["blobs"].bucket_name,
                },
            },
            "logs": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["logs"].bucket_name,
                },
            },
            "backups": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["backups"].bucket_name,
                },
            },
            "default": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["blobs"].bucket_name,
                },
            },
        },
        "autoscaler": {
            "enabled": True,
            "auto_discovery": {
                "cluster_name": eks_cluster_name,
            },
            "groups": [],
            "aws": {
                "region": aws_region,
            },
        },
        "internal_docker_registry": {
            "s3_override": {
                "region": aws_region,
                "bucket": buckets["registry"].bucket_name,
            }
        },
        "gpu": {"enabled": True},
        "services": {
            "nginx_ingress": {},
            "forge": {
                "chart_values": {
                    "config": {
                        "fullPrivilege": True,
                    },
                }
            },
        },
    }

    if r53_zone_ids:
        agent_cfg["external_dns"] = {
            "enabled": True,
            "zone_id_filters": r53_zone_ids,
            "txt_owner_id": r53_owner_id,
        }

    agent_cfg["services"]["nginx_ingress"]["chart_values"] = {
        "controller": {
            "kind": "Deployment",
            "hostNetwork": False,
            "config": {"use-proxy-protocol": "true"},
            "service": {
                "enabled": True,
                "type": "LoadBalancer",
                "annotations": {
                    "service.beta.kubernetes.io/aws-load-balancer-ssl-cert": install.acm_cert_arn or "__FILL__",
                    "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                    "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "tcp",
                    "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                    "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                    "service.beta.kubernetes.io/aws-load-balancer-proxy-protocol": "*",
                    # "service.beta.kubernetes.io/aws-load-balancer-security-groups":
                    #     "could-propagate-this-instead-of-create"
                },
                "targetPorts": {"http": "http", "https": "http"},
                "loadBalancerSourceRanges": access_list,
            },
        }
    }

    if monitoring_bucket:
        agent_cfg["services"]["nginx_ingress"]["chart_values"].update(
            {
                "service.beta.kubernetes.io/aws-load-balancer-access-log-enabled": "true",
                "service.beta.kubernetes.io/aws-load-balancer-access-log-emit-interval": "5",
                "service.beta.kubernetes.io/aws-load-balancer-access-log-s3-bucket-name": monitoring_bucket.bucket_name,
                "service.beta.kubernetes.io/aws-load-balancer-access-log-s3-bucket-prefix": "ELBAccessLogs",
            }
        )

    if install.registry_username:
        agent_cfg["private_docker_registry"] = {
            "server": "quay.io",
            "username": install.registry_username,
            "password": install.registry_password,
        }

    if install.gcr_credentials:
        agent_cfg["helm"] = {
            "version": 3,
            "host": "gcr.io",
            "namespace": "domino-eng-service-artifacts",
            "username": "_json_key",
            "password": install.gcr_credentials,
        }

    return agent_cfg
