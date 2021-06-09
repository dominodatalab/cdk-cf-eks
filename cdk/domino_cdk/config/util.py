from dataclasses import dataclass
from logging import Logger
from typing import List

log = Logger("domino_cdk.config")


def from_loader(name: str, cfg, c: dict):
    if c:
        log.warning(f"Warning: Unused/unsupported config entries in {name}: {c}")
    return cfg


def check_leavins(thing, section, obj):
    if leavins := [x for x in obj if x]:
        log.warning(f"Warning: Unused/unsupported {thing} in {section}: {leavins}")


@dataclass
class MachineImage:
    ami_id: str
    user_data: str


@dataclass
class IngressRule:
    name: str
    from_port: int
    to_port: 22
    protocol: str
    ip_cidrs: List[str]

    @staticmethod
    def load_rules(name: str, rules: List[dict]):
        if not rules:
            return None
        output = [
            IngressRule(r.pop("name"), r.pop("from_port"), r.pop("to_port"), r.pop("protocol"), r.pop("ip_cidrs"))
            for r in rules
        ]
        check_leavins("ingress rules", name, rules)
        return output
