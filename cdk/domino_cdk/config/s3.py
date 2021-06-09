from dataclasses import dataclass
from typing import Dict

from domino_cdk.config.util import from_loader


@dataclass
class S3:
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
