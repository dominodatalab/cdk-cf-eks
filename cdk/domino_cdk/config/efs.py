from dataclasses import dataclass
from typing import Optional

from domino_cdk.config.util import from_loader


@dataclass
class EFS:
    """
    removal_policy_destroy: true/false - Destroy EFS filesystem when destroying CloudFormation stack
    """

    @dataclass
    class Backup:
        """
        enable: true/false - Enable the EFS backup vault, default: true
        schedule: "0 12 * * ? *" - Schedule for efs backups in cron-like format, see here for docs:
                                   https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html#CronExpressions
        move_to_cold_storage_after: 35 - Numberof days (null to disable)
        delete_after: 125 - Number of days, must be 90 days after cold storage (null to disable)
        removal_policy: RETAIN - DESTROY, RETAIN or SNAPSHOT
        """

        enable: bool
        schedule: str
        move_to_cold_storage_after: int
        delete_after: int
        removal_policy: str

    backup: Backup
    removal_policy_destroy: bool

    @staticmethod
    def from_0_0_0(c: dict) -> Optional['EFS']:
        backup = c.pop("backup")
        return from_loader(
            "config.efs",
            EFS(
                backup=EFS.Backup(
                    enable=backup.pop("enable"),
                    schedule=backup.pop("schedule"),
                    move_to_cold_storage_after=backup.pop("move_to_cold_storage_after", None),
                    delete_after=backup.pop("delete_after", None),
                    removal_policy=backup.pop("removal_policy", None),
                ),
                removal_policy_destroy=c.pop("removal_policy_destroy", None),
            ),
            c,
        )
