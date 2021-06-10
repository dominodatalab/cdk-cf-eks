from dataclasses import dataclass, fields, is_dataclass
from typing import Dict, List

from ruamel.yaml.comments import CommentedMap

from domino_cdk import __version__
from domino_cdk.config.efs import EFS
from domino_cdk.config.eks import EKS
from domino_cdk.config.route53 import Route53
from domino_cdk.config.s3 import S3
from domino_cdk.config.vpc import VPC


def from_loader(name: str, cfg, c: dict):
    if c:
        print(f"Warning: Unused/unsupported config entries in {name}: {c}")
    return cfg


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
    availability_zones: List[str]
    tags: Dict[str, str]

    vpc: VPC
    efs: EFS
    route53: Route53
    eks: EKS
    s3: S3

    install: dict

    @staticmethod
    def from_0_0_0(c: dict):
        return from_loader(
            "config",
            DominoCDKConfig(
                schema=__version__,
                name=c.pop("name"),
                aws_region=c.pop("aws_region"),
                aws_account_id=c.pop("aws_account_id"),
                availability_zones=c.pop("availability_zones", []),
                tags=c.pop("tags", {}),
                install=c.pop("install", {}),
                vpc=VPC.from_0_0_0(c.pop("vpc")),
                efs=EFS.from_0_0_0(c.pop("efs")),
                route53=Route53.from_0_0_0(c.pop("route53")),
                eks=EKS.from_0_0_0(c.pop("eks")),
                s3=S3.from_0_0_0(c.pop("s3")),
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
                availability_zones=c.pop("availability_zones", []),
                tags=c.pop("tags", {}),
                install=c.pop("install", {}),
                vpc=VPC.from_0_0_1(c.pop("vpc")),
                efs=EFS.from_0_0_0(c.pop("efs")),
                route53=Route53.from_0_0_0(c.pop("route53")),
                eks=EKS.from_0_0_1(c.pop("eks")),
                s3=S3.from_0_0_0(c.pop("s3")),
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
                cm = CommentedMap({x: r_vars(y, indent) for x, y in vars(c).items()})
                if not disable_comments:
                    [
                        cm.yaml_set_comment_before_after_key(k, after=v.__doc__, after_indent=indent)
                        for k, v in vars(c).items()
                        if is_dataclass(v) and getattr(v, "__doc__")
                    ]
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
                "managed_nodegroups", before=EKS.NodegroupBase.__doc__, indent=2
            )

        return rendered
