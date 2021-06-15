from aws_cdk import core as cdk

from domino_cdk.util import DominoCdkUtil


def generate_install_config(stack: cdk.Stack):
    agent_cfg = {
        "name": stack.name,
        "pod_cidr": stack.vpc_stack.vpc.vpc_cidr_block,
        "global_node_selectors": stack.cfg.eks.global_node_labels,
        "storage_classes": {
            "shared": {
                "efs": {
                    "region": stack.cfg.aws_region,
                    "filesystem_id": stack.efs_stack.outputs["efs"].value,
                }
            },
        },
        "blob_storage": {
            "projects": {
                "s3": {
                    "region": stack.cfg.aws_region,
                    "bucket": stack.s3_stack.buckets["blobs"].bucket_name,
                },
            },
            "logs": {
                "s3": {
                    "region": stack.cfg.aws_region,
                    "bucket": stack.s3_stack.buckets["logs"].bucket_name,
                },
            },
            "backups": {
                "s3": {
                    "region": stack.cfg.aws_region,
                    "bucket": stack.s3_stack.buckets["backups"].bucket_name,
                },
            },
            "default": {
                "s3": {
                    "region": stack.cfg.aws_region,
                    "bucket": stack.s3_stack.buckets["blobs"].bucket_name,
                },
            },
        },
        "autoscaler": {
            "enabled": True,
            "auto_discovery": {
                "cluster_name": stack.eks_stack.cluster.cluster_name,
            },
            "groups": [],
            "aws": {
                "region": stack.cfg.aws_region,
            },
        },
        "internal_docker_registry": {
            "s3_override": {
                "region": stack.cfg.aws_region,
                "bucket": stack.s3_stack.buckets["registry"].bucket_name,
            }
        },
        "services": {
            "nginx_ingress": {},
            "nucleus": {
                "chart_values": {
                    "keycloak": {
                        "createIntegrationTestUser": True,
                    }
                }
            },
            "forge": {
                "chart_values": {
                    "config": {
                        "fullPrivilege": True,
                    },
                }
            },
        },
    }

    if stack.cfg.route53.zone_ids:
        agent_cfg["external_dns"] = {
            "enabled": True,
            "zone_id_filters": stack.cfg.route53.zone_ids,
            "txt_owner_id": stack.eks_stack.outputs["route53-txt-owner-id"].value,
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
                    "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                    "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "tcp",
                    "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                    "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                    "service.beta.kubernetes.io/aws-load-balancer-proxy-protocol": "*",
                    # "service.beta.kubernetes.io/aws-load-balancer-security-groups":
                    #     "could-propagate-this-instead-of-create"
                },
                "targetPorts": {"http": "http", "https": "http"},
                "loadBalancerSourceRanges": ["0.0.0.0/0"],  # TODO AF
            },
        }
    }

    return DominoCdkUtil.deep_merge(agent_cfg, stack.cfg.install)
