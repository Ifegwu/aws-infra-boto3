from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProvisionConfig:
    region: str
    key_name: str
    instance_type: str
    name_tag: str
    subnet_id: str | None
    security_group_ids: list[str] | None
    ami_id: str | None
    create_dev_security_group: bool
    open_ports: list[int]
    user_data: str | None
    wait_running: bool
    allocate_eip: bool
    dry_run: bool

