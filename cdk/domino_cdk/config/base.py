from dataclasses import dataclass, fields, is_dataclass
from textwrap import dedent
from typing import Dict

from field_properties import field_property, unwrap_property
from ruamel.yaml.comments import CommentedMap

from domino_cdk import __version__
from domino_cdk.config.efs import EFS
from domino_cdk.config.eks import EKS
from domino_cdk.config.install import Install
from domino_cdk.config.route53 import Route53
from domino_cdk.config.s3 import S3
from domino_cdk.config.util import from_loader
from domino_cdk.config.vpc import VPC


@dataclass
class MachineImage:
    ami_id: str
    user_data: str


@dataclass
class DominoCDKConfig:
    schema: str
    name: str
    aws_region: str
    aws_account_id: str

    tags: Dict[str, str] = field_property(default={})

    create_iam_roles_for_service_accounts: bool = False

    vpc: VPC = None
    efs: EFS = None
    route53: Route53 = None
    eks: EKS = None
    s3: S3 = None

    install: Install = None

    @field_property(tags)
    def get_tags(self) -> Dict[str, str]:
        return {**unwrap_property(self).tags, **{"domino-deploy-id": self.name}}

    def set_tags(self, tags: int):
        if "domino-deploy-id" in tags:
            raise ValueError("Tag domino-deploy-id cannot be overridden")
        unwrap_property(self).tags = tags

    field_property(tags).setter(set_tags)

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
                schema=__version__,
                name=c.pop("name"),
                aws_region=c.pop("aws_region"),
                aws_account_id=c.pop("aws_account_id"),
                tags=c.pop("tags", {}),
                create_iam_roles_for_service_accounts=False,
                vpc=VPC.from_0_0_0({**c.pop("vpc"), **{"availability_zones": c.pop("availability_zones", [])}}),
                efs=EFS.from_0_0_0(c.pop("efs")),
                route53=Route53.from_0_0_0(c.pop("route53")),
                eks=EKS.from_0_0_0(c.pop("eks")),
                s3=S3.from_0_0_0(c.pop("s3")),
                install=Install.from_0_0_0(c.pop("install")),
            ),
            c,
        )

    @staticmethod
    def from_0_0_1(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
                schema=__version__,
                name=c.pop("name"),
                aws_region=c.pop("aws_region"),
                aws_account_id=c.pop("aws_account_id"),
                tags=c.pop("tags", {}),
                create_iam_roles_for_service_accounts=c.pop("create_iam_roles_for_service_accounts", False),
                vpc=VPC.from_0_0_1(c.pop("vpc")),
                efs=EFS.from_0_0_0(c.pop("efs")),
                route53=Route53.from_0_0_0(c.pop("route53")),
                eks=EKS.from_0_0_1(c.pop("eks")),
                s3=S3.from_0_0_0(c.pop("s3")),
                install=Install.from_0_0_1(c.pop("install")),
            ),
            c,
        )

    def __post_init__(self):
        errors = []

        def val(path: str, obj):
            for f in fields(obj):
                value = getattr(obj, f.name)
                if is_dataclass(value):
                    val(f"{path}.{f.name}", value)
                elif not value:
                    continue
                # TODO: Actually do the full check (ie List[str], etc.)
                elif getattr(f.type, "_name", None) == "List":
                    if type(value) is not list:
                        errors.append(
                            f"{path}.{f.name} type ({f.type}) does not match value: [{value}] ({type(value)})"
                        )
                    else:
                        [val(f"{path}.{f.name}.[{i}]", x) for i, x in enumerate(value) if is_dataclass(x)]
                elif getattr(f.type, "_name", None) == "Dict":
                    if type(value) not in [dict, CommentedMap]:
                        errors.append(
                            f"{path}.{f.name} type ({f.type}) does not match value: [{value}] ({type(value)})"
                        )
                    else:
                        [val(f"{path}.{f.name}.{k}", v) for k, v in value.items() if is_dataclass(v)]
                elif value and f.type != type(value):
                    errors.append(f"{path}.{f.name} type ({f.type}) does not match value: [{value}] ({type(value)})")

        val("config", self)
        if errors:
            raise ValueError("\n".join(errors))

    def render(self, disable_comments: bool = False):
        def r_vars(c, indent: int):
            indent += 2
            if is_dataclass(c):
                hidden = getattr(c, "_hidden", [])
                cm = CommentedMap(
                    {
                        (x if x != "_tags" else "tags"): r_vars(y, indent)
                        for x, y in vars(c).items()
                        if x not in hidden or y
                    }
                )
                if not disable_comments:
                    [
                        cm.yaml_set_comment_before_after_key(k, after=dedent(v.__doc__).strip(), after_indent=indent)
                        for k, v in vars(c).items()
                        if is_dataclass(v) and getattr(v, "__doc__") and not getattr(v, "_no_doc", False)
                    ]
                else:
                    print(getattr(c, "_no_doc", False))
                    print(getattr(c, "__doc__"))
                return cm
            elif type(c) == list:
                return [r_vars(x, indent) for x in c]
            elif type(c) == dict:
                return CommentedMap({x: r_vars(y, indent) for x, y in c.items()})
            else:
                return c

        rendered = r_vars(self, 0)

        if not disable_comments:
            rendered["eks"].yaml_set_comment_before_after_key(
                "managed_nodegroups", before=dedent(EKS.NodegroupBase.__doc__).strip(), indent=2
            )

        return rendered
