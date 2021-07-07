from filecmp import cmp
from glob import glob
from json import loads as json_loads
from os import path
from os.path import basename, isfile
from os.path import join as path_join
from subprocess import run
from time import time
from typing import Dict, List
from urllib.parse import urlparse

import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_logs as logs
import aws_cdk.custom_resources as cr
from aws_cdk import core as cdk


class ExternalCommandException(Exception):
    """Exception running spawned external commands"""


class DominoCdkUtil:
    @staticmethod
    def load_manifest(manifest_file):
        with open(manifest_file) as f:
            try:
                artifacts = json_loads(f.read())["artifacts"]
                artifacts.pop("Tree")
                stack_name = list(artifacts)[0]
                env = artifacts[stack_name]["environment"]
                aws_region = basename(urlparse(env).path)
                metadata = artifacts[stack_name]["metadata"][f"/{stack_name}"]
            except Exception:
                raise KeyError(f"Cannot parse CDK asset manifest {manifest_file}!")
            return {"name": stack_name, "region": aws_region, "metadata": metadata}

    @classmethod
    def generate_asset_parameters(cls, asset_dir: str, asset_bucket: str, cfg: dict = None):
        if not cfg:
            cfg = cls.load_manifest(path_join(asset_dir, "manifest.json"))

        parameters = {}

        for c in cfg["metadata"]:
            if c["type"] == "aws:cdk:asset":
                d = c["data"]
                path = d['path']
                if ".zip" not in path and ".json" not in path and not isfile(path_join(asset_dir, "path.zip")):
                    shell_command = f"cd {asset_dir}/{path}/ && zip -9r {path}.zip ./* && mv {path}.zip ../"
                    output = run(shell_command, shell=True, capture_output=True)
                    if output.returncode:
                        raise ExternalCommandException(
                            f"Error running: {shell_command}\nretval: {output.returncode}\nstdout: {output.stdout.decode()}\nstderr: {output.stderr.decode()}"
                        )
                    path = f"{path}.zip"
                parameters[d['artifactHashParameter']] = d['sourceHash']
                parameters[d['s3BucketParameter']] = asset_bucket
                parameters[d['s3KeyParameter']] = f"||{path}"

        return parameters

    # disable_random_templates is a negative flag that's False by default to facilitate the naive cli access (ie any parameter given triggers it)
    @classmethod
    def generate_terraform_bootstrap(
        cls,
        module_path: str,
        asset_bucket: str,
        asset_dir: str,
        aws_region: str,
        output_dir: str,
        disable_random_templates: bool = False,
        iam_role_arn: str = "",
        iam_policy_paths: List[str] = None,
    ):
        cfg = cls.load_manifest(path_join(asset_dir, "manifest.json"))
        stack_name = cfg["name"]

        if not aws_region:
            aws_region = cfg["region"]

            if aws_region == "unknown-region":
                raise Exception("Please provide region")

        asset_parameters = cls.generate_asset_parameters(asset_dir, asset_bucket, cfg)
        template_filename = path_join(asset_dir, f"{stack_name}.template.json")

        if not disable_random_templates:
            template_files = sorted(glob(f"{asset_dir}/{stack_name}-*.template.json"))
            last_template_file = template_files[-1] if template_files else None

            # Generate new timestamped template file?
            if not last_template_file or not cmp(template_filename, last_template_file):
                ts_template_filename = f"{stack_name}-{int(time())}.template.json"
                shell_command = f"cp {template_filename} {asset_dir}/{ts_template_filename}"
                output = run(shell_command, shell=True, capture_output=True)
                if output.returncode:
                    raise ExternalCommandException(
                        f"Error running: {shell_command}\nretval: {output.returncode}\nstdout: {output.stdout.decode()}\nstderr: {output.stderr.decode()}"
                    )
                template_filename = ts_template_filename
            else:
                template_filename = last_template_file
        return {
            "module": {
                "cdk": {
                    "source": module_path,
                    "asset_bucket": asset_bucket,
                    "asset_dir": asset_dir,
                    "aws_region": aws_region,
                    "name": stack_name,
                    "iam_role_arn": iam_role_arn,
                    "iam_policy_paths": iam_policy_paths,
                    "parameters": asset_parameters,
                    "template_filename": basename(template_filename),
                    "output_dir": output_dir,
                },
            },
            "output": {
                "cloudformation_outputs": {
                    "value": "${module.cdk.cloudformation_outputs}",
                }
            },
        }

    @classmethod
    def deep_merge(cls, *dictionaries) -> dict:
        """
        Recursive dict merge.

        Takes any number of dictionaries as arguments. Each subsequent dictionary will be overlaid on the previous ones
        before. Therefore, the rightmost dictionary's value will take precedence. None values will be interpreted as
        empty dictionaries, but otherwise arguments provided must be of the dict type.
        """

        def check_type(dx) -> dict:
            if dx is None:
                dx = {}
            if not isinstance(dx, dict):
                raise TypeError("Must provide only dictionaries!")
            return dx

        def merge(alpha, omega, key):
            if isinstance(alpha.get(key), dict) and isinstance(omega[key], dict):
                return cls.deep_merge(alpha[key], omega[key])
            else:
                return omega[key]

        def overlay(alpha: dict, omega: dict) -> dict:
            return {**alpha, **{k: merge(alpha, omega, k) for k, _ in omega.items()}}

        if 0 == len(dictionaries):
            return {}
        base_dict = check_type(dictionaries[0])
        return base_dict if len(dictionaries) == 1 else overlay(base_dict, cls.deep_merge(*dictionaries[1:]))

    @staticmethod
    def create_lambda(
        scope: cdk.Construct,
        stack_name: str,
        dirname: str,
        name: str,
        environment: Dict[str, str],
        resources: List[str],
        actions: List[str],
    ) -> cdk.Construct:
        with open(path.join(dirname, "lambda", name + ".py"), encoding="utf-8") as fp:
            on_event_code_body = fp.read()
        on_event = lambda_.Function(
            scope,
            name + "_on_event",
            function_name=f"{stack_name}-{name}",
            runtime=lambda_.Runtime.PYTHON_3_7,
            handler="index.on_event",
            code=lambda_.InlineCode(on_event_code_body),
            environment=environment,
            timeout=cdk.Duration.seconds(600),  # default is 3 seconds
            log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
        )
        statement = iam.PolicyStatement()
        for r in resources:
            statement.add_resources(r)
        for a in actions:
            statement.add_actions(a)
        on_event.add_to_role_policy(statement)

        is_complete = None
        try:
            with open(path.join(dirname, "lambda", name + "_is_complete.py"), encoding="utf-8") as fp:
                is_complete_code_body = fp.read()
            is_complete = lambda_.Function(
                scope,
                name + "_is_complete",
                runtime=lambda_.Runtime.PYTHON_3_7,
                handler="index.is_complete",
                code=lambda_.InlineCode(is_complete_code_body),
                # timeout defaults to 2 minutes
                log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
            )
            is_complete.add_to_role_policy(statement)
        except FileNotFoundError:
            pass

        provider = cr.Provider(
            scope,
            name + "_provider",
            on_event_handler=on_event,
            is_complete_handler=is_complete,
            log_retention=logs.RetentionDays.ONE_DAY,  # default is INFINITE
        )

        return cdk.CustomResource(scope, name + "_custom", service_token=provider.service_token)
