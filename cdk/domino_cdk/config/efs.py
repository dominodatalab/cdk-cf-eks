from dataclasses import dataclass

from domino_cdk.config.util import from_loader


@dataclass
class EFS:
    @dataclass
    class Backup:
        enable: bool
        schedule: str
        move_to_cold_storage_after: int
        delete_after: int
        removal_policy: str

    backup: Backup
    removal_policy_destroy: bool

    @staticmethod
    def from_0_0_1(c: dict):
        backup = c.pop("backup")
        return from_loader(
            "config.efs",
            EFS(
                backup=EFS.Backup(
                    enable=backup.pop("enable"),
                    schedule=backup.pop("schedule"),
                    move_to_cold_storage_after=backup.pop("move_to_cold_storage_after"),
                    delete_after=backup.pop("delete_after"),
                    removal_policy=backup.pop("removal_policy"),
                ),
                removal_policy_destroy=c.pop("removal_policy_destroy", None),
            ),
            c,
        )
