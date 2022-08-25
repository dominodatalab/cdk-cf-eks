from unittest import TestCase

from aws_cdk.aws_s3 import Bucket
from aws_cdk.core import App, Environment, Stack

from domino_cdk.agent import generate_install_config
from domino_cdk.config import Install


class TestAgent(TestCase):
    maxDiff = None

    def setUp(self):
        self.app = App()
        self.stack = Stack(self.app, "VPC", env=Environment(region="us-west-2", account="1234567890"))
        self.buckets = {
            "blobs": Bucket(self.stack, "s3-blobs"),
            "logs": Bucket(self.stack, "s3-logs"),
            "backups": Bucket(self.stack, "s3-backups"),
            "registry": Bucket(self.stack, "s3-registry"),
        }

    def test_generate_install_config_istio(self):
        config = generate_install_config(
            "test",
            Install(
                access_list="0.0.0.0/0",
                acm_cert_arn="acm:cert:arn",
                hostname="test.example.com",
                registry_username=None,
                registry_password=None,
                overrides={},
                istio_compatible=True,
            ),
            "us-west-2",
            "test-cluster",
            "10.0.0.0/16",
            {},
            self.buckets,
            None,
            "efs:ap-id",
            "ZONE-ABC",
            "TXTOWNER",
        )

        self.assertEqual(config["istio"], {"enabled": True, "install": True, "cni": False})
        self.assertEqual(
            config["services"]["nginx_ingress"]["chart_values"],
            {
                "controller": {
                    "kind": "Deployment",
                    "hostNetwork": False,
                    "service": {
                        "enabled": True,
                        "type": "LoadBalancer",
                        "targetPorts": {"http": "http", "https": "https"},
                        "annotations": {
                            "service.beta.kubernetes.io/aws-load-balancer-ssl-negotiation-policy": "ELBSecurityPolicy-TLS-1-2-2017-01",
                            "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "ssl",
                            "service.beta.kubernetes.io/aws-load-balancer-ssl-cert": "acm:cert:arn",
                            "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                            "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                            "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                        },
                        "loadBalancerSourceRanges": "0.0.0.0/0",
                    },
                    "config": {
                        "use-proxy-protocol": "false",
                        "ssl-ciphers": "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA384:AES128-GCM-SHA256:AES128-SHA256:AES256-GCM-SHA384:AES256-SHA256:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!aECDH:!EDH-DSS-DES-CBC3-SHA:!EDH-RSA-DES-CBC3-SHA:!KRB5-DES-CBC3-SHA",  # noqa
                        "ssl-protocols": "TLSv1.2 TLSv1.3",
                    },
                }
            },
        )

    def test_generate_install_config(self):
        config = generate_install_config(
            "test",
            Install(
                access_list="0.0.0.0/0",
                acm_cert_arn="acm:cert:arn",
                hostname="test.example.com",
                registry_username=None,
                registry_password=None,
                overrides={},
                istio_compatible=False,
            ),
            "us-west-2",
            "test-cluster",
            "10.0.0.0/16",
            {},
            self.buckets,
            None,
            "efs:ap-id",
            "ZONE-ABC",
            "TXTOWNER",
        )

        self.assertEqual(config.get("istio"), None)
        self.assertEqual(
            config["services"]["nginx_ingress"]["chart_values"],
            {
                "controller": {
                    "kind": "Deployment",
                    "hostNetwork": False,
                    "service": {
                        "enabled": True,
                        "type": "LoadBalancer",
                        "targetPorts": {"http": "http", "https": "http"},
                        "annotations": {
                            "service.beta.kubernetes.io/aws-load-balancer-ssl-negotiation-policy": "ELBSecurityPolicy-TLS-1-2-2017-01",
                            "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "tcp",
                            "service.beta.kubernetes.io/aws-load-balancer-ssl-cert": "acm:cert:arn",
                            "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                            "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                            "service.beta.kubernetes.io/aws-load-balancer-proxy-protocol": "*",
                            "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                        },
                        "loadBalancerSourceRanges": "0.0.0.0/0",
                    },
                    "config": {
                        "use-proxy-protocol": "true",
                    },
                }
            },
        )
