from typing import Any, Dict, Optional

from aws_cdk.aws_s3 import Bucket

from domino_cdk.config import Install
from domino_cdk.util import DominoCdkUtil


def generate_install_config(
    name: str,
    install: Install,
    aws_region: str,
    eks_cluster_name: str,
    pod_cidr: str,
    global_node_selectors: Dict[str, str],
    buckets: Dict[str, Bucket],
    monitoring_bucket: Optional[Bucket],
    efs_fsid: str,
    efs_apid: str,
    r53_zone_ids: str,
    r53_owner_id: str,
) -> Dict:
    agent_cfg: Dict[str, Any] = {
        "name": name,
        "schema": "1.1",
        "hostname": install.hostname,
        "pod_cidr": pod_cidr,
        "global_node_selectors": global_node_selectors,
        "storage_classes": {
            "shared": {
                "efs": {
                    "region": aws_region,
                    "filesystem_id": efs_fsid,
                    "access_point_id": efs_apid,
                }
            },
        },
        "blob_storage": {
            "projects": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["blobs"].bucket_name,
                    "sse_kms_key_id": None,
                },
            },
            "logs": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["logs"].bucket_name,
                    "sse_kms_key_id": None,
                },
            },
            "backups": {
                "s3": {
                    "region": aws_region,
                    "bucket": buckets["backups"].bucket_name,
                    "sse_kms_key_id": None,
                },
            },
        },
        "autoscaler": {
            "cloud_provider": "aws",
            "auto_discovery": {
                "cluster_name": eks_cluster_name,
            },
            "groups": [],
            "aws": {
                "region": aws_region,
            },
        },
        "internal_docker_registry": {
            "enabled": True,
            "s3_override": {
                "region": aws_region,
                "bucket": buckets["registry"].bucket_name,
                "sse_kms_key_id": None,
            },
        },
        "metrics_server": {"install": True},
        "gpu": {"enabled": True},
        "release_overrides": {
            "nginx-ingress": {},
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
            "provider": "aws",
            "zone_id_filters": r53_zone_ids,
            "txt_owner_id": r53_owner_id,
        }

    agent_cfg["release_overrides"]["nginx-ingress"]["chart_values"] = {
        "controller": {
            "kind": "Deployment",
            "hostNetwork": False,
            "service": {
                "enabled": True,
                "type": "LoadBalancer",
                "annotations": {
                    "service.beta.kubernetes.io/aws-load-balancer-ssl-cert": install.acm_cert_arn or "__FILL__",
                    "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                    "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "tcp",
                    "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                    "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                    # "service.beta.kubernetes.io/aws-load-balancer-security-groups":
                    #     "could-propagate-this-instead-of-create"
                },
                "loadBalancerSourceRanges": install.access_list,
            },
        }
    }

    if install.istio_compatible:
        agent_cfg["istio"] = {
            "enabled": True,
            "install": True,
            "cni": False,
        }

        agent_cfg = DominoCdkUtil.deep_merge(
            agent_cfg,
            {
                "release_overrides": {
                    "nginx-ingress": {
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

    else:
        agent_cfg = DominoCdkUtil.deep_merge(
            agent_cfg,
            {
                "release_overrides": {
                    "nginx-ingress": {
                        "chart_values": {
                            "controller": {
                                "config": {
                                    "use-proxy-protocol": "true",
                                },
                                "service": {
                                    "targetPorts": {"http": "http", "https": "http"},
                                    "annotations": {
                                        "service.beta.kubernetes.io/aws-load-balancer-proxy-protocol": "*",
                                    },
                                },
                            }
                        }
                    }
                }
            },
        )

    if monitoring_bucket:
        agent_cfg["release_overrides"]["nginx-ingress"]["chart_values"]["controller"]["service"]["annotations"].update(
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

    return agent_cfg
