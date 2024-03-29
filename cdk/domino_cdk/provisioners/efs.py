import aws_cdk.aws_backup as backup
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_efs as efs
import aws_cdk.aws_events as events
import aws_cdk.aws_iam as iam
from aws_cdk import CfnOutput, Duration, NestedStack, RemovalPolicy
from aws_cdk.region_info import Fact, FactName
from constructs import Construct

from domino_cdk import config

from .lambda_utils import create_lambda

_DominoEfsStack = None


class DominoEfsProvisioner:
    def __init__(
        self,
        parent: Construct,
        construct_id: str,
        stack_name: str,
        cfg: config.EFS,
        vpc: ec2.Vpc,
        security_group: ec2.SecurityGroup,
        nest: bool,
        **kwargs,
    ):
        self.parent = parent
        self.scope = NestedStack(self.parent, construct_id, **kwargs) if nest else self.parent

        self.provision_efs(stack_name, cfg, vpc, security_group)
        if cfg.backup.enable:
            self.provision_backup_vault(stack_name, cfg.backup)

    def provision_efs(self, stack_name: str, cfg: config.EFS, vpc: ec2.Vpc, security_group: ec2.SecurityGroup):
        self.efs = efs.FileSystem(
            self.scope,
            "Efs",
            vpc=vpc,
            encrypted=True,
            file_system_name=stack_name,
            # kms_key,
            # lifecycle_policy,
            removal_policy=RemovalPolicy.DESTROY if cfg.removal_policy_destroy else RemovalPolicy.RETAIN,
            security_group=security_group,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            throughput_mode=efs.ThroughputMode.BURSTING,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
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

    def provision_backup_vault(self, stack_name: str, efs_backup: config.EFS.Backup):
        partition = Fact.require_fact(self.scope.region, FactName.PARTITION)

        vault = backup.BackupVault(
            self.scope,
            "efs_backup",
            backup_vault_name=f"{stack_name}-efs",
            removal_policy=RemovalPolicy[efs_backup.removal_policy or RemovalPolicy.RETAIN.value],
        )

        CfnOutput(self.parent, "backup-vault", value=vault.backup_vault_name)
        plan = backup.BackupPlan(
            self.scope,
            "efs_backup_plan",
            backup_plan_name=f"{stack_name}-efs",
            backup_plan_rules=[
                backup.BackupPlanRule(
                    backup_vault=vault,
                    delete_after=Duration.days(d) if (d := efs_backup.delete_after) else None,
                    move_to_cold_storage_after=Duration.days(d)
                    if (d := efs_backup.move_to_cold_storage_after)
                    else None,
                    rule_name="efs-rule",
                    schedule_expression=events.Schedule.expression(f"cron({efs_backup.schedule})"),
                    start_window=Duration.hours(1),
                    completion_window=Duration.hours(3),
                )
            ],
        )

        backupRole = iam.Role(
            self.scope,
            "efs_backup_role",
            assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
            role_name=f"{stack_name}-efs-backup",
        )
        backup.BackupSelection(
            self.scope,
            "efs_backup_selection",
            backup_plan=plan,
            resources=[backup.BackupResource.from_efs_file_system(self.efs)],
            allow_restores=False,
            backup_selection_name=f"{stack_name}-efs",
            role=backupRole,
        )

        create_lambda(
            scope=self.scope,
            stack_name=stack_name,
            name="backup_post_creation_tasks",
            properties={"stack_name": stack_name, "backup_vault": vault.backup_vault_name},
            resources=[
                f"arn:{partition}:backup:{self.scope.region}:{self.scope.account}:backup-vault:{stack_name}-efs",
                # To limit the recovery points, we will need to add tag checking condition to the IAM policy for the
                # lambda. I think it will be a bit of overkill
                f"arn:{partition}:backup:{self.scope.region}:{self.scope.account}:recovery-point:*",
            ],
            actions=[
                "backup:ListRecoveryPointsByBackupVault",
                "backup:DeleteRecoveryPoint",
            ],
        )
