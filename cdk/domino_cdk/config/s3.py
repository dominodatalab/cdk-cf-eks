from dataclasses import dataclass
from typing import Dict

from domino_cdk.config.util import from_loader


@dataclass
class S3:
    """
    Map of buckets to create and provide IAM access from the EKS cluster.
    Bucket parameters:
    auto_delete_objects: true/false - Delete entire contents of bucket when destroying the CloudFormation stack
    removal_policy_destroy: true/false - Delete bucket when destroying stack. If auto_delete_objects is false,
                                         destroys will fail unless buckets are emptied.
    sse_kms_key_id: XXX - Specific KMS key ID to setup with bucket. Otherwise, defaults to AES256
    """

    @dataclass
    class Bucket:
        auto_delete_objects: bool
        removal_policy_destroy: bool
        sse_kms_key_id: str

    buckets: Dict[str, Bucket]

    @staticmethod
    def from_0_0_0(c: dict):
        buckets = c.pop("buckets")
        return from_loader(
            "config.s3",
            S3(
                buckets={
                    name: S3.Bucket(
                        auto_delete_objects=b.pop("auto_delete_objects", False),
                        removal_policy_destroy=b.pop("removal_policy_destroy", False),
                        sse_kms_key_id=b.pop("sse_kms_key_id", None),
                    )
                    for name, b in buckets.items()
                }
            ),
            c,
        )
