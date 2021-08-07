from dataclasses import dataclass
from typing import Dict, Optional

from domino_cdk.config.util import check_leavins, from_loader


@dataclass
class S3:
    """
    Map of buckets to create and provide IAM access from the EKS cluster.

    "blobs", "logs", "backups" and "registry" buckets are MANDATORY.

    The "monitoring" bucket is optionally created to store various operational logs: VPC flow logs, S3 and ELB access logs.

    Bucket parameters:
    name: "my-bucket-name" - Optional name to override default bucketname of deployname-bucket-type
    auto_delete_objects: true/false - Delete entire contents of bucket when destroying the CloudFormation stack
    removal_policy_destroy: true/false - Delete bucket when destroying stack. If auto_delete_objects is false,
                                         destroys will fail unless buckets are emptied.
    sse_kms_key_id: XXX - Specific KMS key ID to setup with bucket. Otherwise, defaults to AES256
    """

    @dataclass
    class BucketList:
        @dataclass
        class Bucket:
            auto_delete_objects: bool
            removal_policy_destroy: bool
            sse_kms_key_id: Optional[str]
            name: str = None
            _hidden = ["name"]
            _no_doc = True

        blobs: Bucket
        logs: Bucket
        backups: Bucket
        registry: Bucket
        monitoring: Bucket
        _no_doc = True

        @classmethod
        def load(cls, buckets: Dict[str, Bucket]):
            def _bucket(b: dict) -> S3.BucketList.Bucket:
                if not b:
                    return
                b_out = S3.BucketList.Bucket(
                    auto_delete_objects=b.pop("auto_delete_objects", False),
                    removal_policy_destroy=b.pop("removal_policy_destroy", False),
                    sse_kms_key_id=b.pop("sse_kms_key_id", None),
                    name=b.pop("name", None),
                )
                check_leavins("s3 bucket attribute", "config.s3.buckets.bucket", b)
                return b_out

            out = cls(
                blobs=_bucket(buckets.pop("blobs")),
                logs=_bucket(buckets.pop("logs")),
                backups=_bucket(buckets.pop("backups")),
                registry=_bucket(buckets.pop("registry")),
                monitoring=_bucket(buckets.pop("monitoring", None)),
            )
            check_leavins("s3 bucket", "config.s3.buckets", buckets)
            return out

    buckets: BucketList

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config.s3",
            S3(buckets=S3.BucketList.load(c.pop("buckets"))),
            c,
        )
