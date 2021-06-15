import aws_cdk.aws_backup as backup
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_efs as efs
import aws_cdk.aws_events as events
import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk

from domino_cdk.config.efs import EFS


class DominoEfsStack(cdk.NestedStack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        name: str,
        cfg: EFS,
        vpc: ec2.Vpc,
        security_group: ec2.SecurityGroup,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.outputs = {}
        self.provision_efs(name, cfg, vpc, security_group)
        if cfg.backup.enable:
            self.provision_backup_vault(name, cfg.backup)

    def provision_efs(self, name: str, cfg: EFS, vpc: ec2.Vpc, security_group: ec2.SecurityGroup):
        self.efs = efs.FileSystem(
            self,
            "Efs",
            vpc=vpc,
            # encrypted=True,
            file_system_name=name,
            # kms_key,
            # lifecycle_policy,
            performance_mode=efs.PerformanceMode.MAX_IO,
            provisioned_throughput_per_second=cdk.Size.mebibytes(100),  # TODO: dev/nondev sizing
            removal_policy=cdk.RemovalPolicy.DESTROY if cfg.removal_policy_destroy else cdk.RemovalPolicy.RETAIN,
            security_group=security_group,
            throughput_mode=efs.ThroughputMode.PROVISIONED,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE),
        )

        self.efs_access_point = self.efs.add_access_point(
            "access_point",
            create_acl=efs.Acl(
                owner_uid="0",
                owner_gid="0",
                permissions="777",
            ),
            path="/domino",
            posix_user=efs.PosixUser(
                uid="0",
                gid="0",
                # secondary_gids
            ),
        )

        self.outputs["efs"] = cdk.CfnOutput(
            self,
            "efs-output",
            value=f"{self.efs.file_system_id}::{self.efs_access_point.access_point_id}",
        )

    def provision_backup_vault(self, name: str, efs_backup: EFS.Backup):
        vault = backup.BackupVault(
            self,
            "efs_backup",
            backup_vault_name=f'{name}-efs',
            removal_policy=cdk.RemovalPolicy[efs_backup.removal_policy or cdk.RemovalPolicy.RETAIN.value],
        )
        cdk.CfnOutput(self, "backup-vault", value=vault.backup_vault_name)
        plan = backup.BackupPlan(
            self,
            "efs_backup_plan",
            backup_plan_name=f"{name}-efs",
            backup_plan_rules=[
                backup.BackupPlanRule(
                    backup_vault=vault,
                    delete_after=cdk.Duration.days(d) if (d := efs_backup.delete_after) else None,
                    move_to_cold_storage_after=cdk.Duration.days(d)
                    if (d := efs_backup.move_to_cold_storage_after)
                    else None,
                    rule_name="efs-rule",
                    schedule_expression=events.Schedule.expression(f"cron({efs_backup.schedule})"),
                    start_window=cdk.Duration.hours(1),
                    completion_window=cdk.Duration.hours(3),
                )
            ],
        )

        backupRole = iam.Role(
            self,
            "efs_backup_role",
            assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
            role_name=f"{name}-efs-backup",
        )
        backup.BackupSelection(
            self,
            "efs_backup_selection",
            backup_plan=plan,
            resources=[backup.BackupResource.from_efs_file_system(self.efs)],
            allow_restores=False,
            backup_selection_name=f"{name}-efs",
            role=backupRole,
        )
