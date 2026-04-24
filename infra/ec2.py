from __future__ import annotations

from typing import Any

import boto3

from infra.ami import get_al2023_ami_id
from infra.models import ProvisionConfig
from infra.network import ensure_dev_security_group, resolve_vpc_and_subnet


def _instance_summary(instance: dict[str, Any], image_id: str, subnet_id: str, sg_ids: list[str]) -> dict[str, Any]:
    return {
        'InstanceId': instance['InstanceId'],
        'State': instance['State']['Name'],
        'PrivateIpAddress': instance.get('PrivateIpAddress'),
        'PublicIpAddress': instance.get('PublicIpAddress'),
        'ImageId': image_id,
        'SubnetId': subnet_id,
        'SecurityGroupIds': sg_ids,
    }


def _read_user_data(user_data_file: str | None) -> str | None:
    if not user_data_file:
        return None
    with open(user_data_file, encoding='utf-8') as f:
        return f.read()


def _refresh_instance(ec2: Any, instance_id: str) -> dict[str, Any]:
    d = ec2.describe_instances(InstanceIds=[instance_id])
    return d['Reservations'][0]['Instances'][0]


def _attach_eip(ec2: Any, instance_id: str) -> str:
    alloc = ec2.allocate_address(Domain='vpc')
    ec2.associate_address(InstanceId=instance_id, AllocationId=alloc['AllocationId'])
    return alloc['PublicIp']


def deploy_ec2_instance(cfg: ProvisionConfig) -> dict[str, Any]:
    ec2 = boto3.client('ec2', region_name=cfg.region)
    ssm = boto3.client('ssm', region_name=cfg.region)
    image_id = cfg.ami_id or get_al2023_ami_id(ssm)
    user_data = _read_user_data(cfg.user_data)

    if cfg.security_group_ids:
        sg_ids = list(cfg.security_group_ids)
        if not cfg.subnet_id:
            raise ValueError('When using custom security groups, pass --subnet-id as well.')
        subnet_id = cfg.subnet_id
    else:
        vpc_id, subnet_id = resolve_vpc_and_subnet(ec2, cfg.subnet_id)
        if not cfg.create_dev_security_group:
            raise RuntimeError(
                'Pass --security-group-id or use --create-dev-security-group '
                '(opens selected ports to 0.0.0.0/0).'
            )
        sg = ensure_dev_security_group(
            ec2,
            vpc_id=vpc_id,
            name=f'{cfg.name_tag}-dev',
            description=f'Temporary dev access for {cfg.name_tag} (restrict in production)',
            open_ports=cfg.open_ports,
        )
        sg_ids = [sg]

    run_kw: dict[str, Any] = {
        'ImageId': image_id,
        'MinCount': 1,
        'MaxCount': 1,
        'InstanceType': cfg.instance_type,
        'KeyName': cfg.key_name,
        'SubnetId': subnet_id,
        'SecurityGroupIds': sg_ids,
        'TagSpecifications': [
            {'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': cfg.name_tag}]}
        ],
        'DryRun': cfg.dry_run,
    }
    if user_data:
        run_kw['UserData'] = user_data

    resp = ec2.run_instances(**run_kw)
    instance = resp['Instances'][0]
    out = _instance_summary(instance, image_id, subnet_id, sg_ids)

    if cfg.wait_running:
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance['InstanceId']])
        instance = _refresh_instance(ec2, instance['InstanceId'])
        out = _instance_summary(instance, image_id, subnet_id, sg_ids)

    if cfg.allocate_eip:
        if not cfg.wait_running:
            waiter = ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance['InstanceId']])
        out['ElasticIp'] = _attach_eip(ec2, instance['InstanceId'])

    return out

