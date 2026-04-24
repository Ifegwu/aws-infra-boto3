from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError


def default_vpc_id(ec2: Any) -> str | None:
    r = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    vpcs = r.get('Vpcs') or []
    return vpcs[0]['VpcId'] if vpcs else None


def pick_subnet_in_vpc(ec2: Any, vpc_id: str) -> str | None:
    r = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    subnets = r.get('Subnets') or []
    if not subnets:
        return None
    subnets.sort(key=lambda s: s['SubnetId'])
    return subnets[0]['SubnetId']


def resolve_vpc_and_subnet(ec2: Any, subnet_id: str | None) -> tuple[str, str]:
    if subnet_id:
        sn_info = ec2.describe_subnets(SubnetIds=[subnet_id])
        subs = sn_info.get('Subnets') or []
        if not subs:
            raise RuntimeError(f'Subnet not found: {subnet_id}')
        return subs[0]['VpcId'], subnet_id

    vpc_id = default_vpc_id(ec2)
    if not vpc_id:
        raise RuntimeError(
            'No default VPC in this account/region. Pass --subnet-id and --security-group-id.'
        )
    sn = pick_subnet_in_vpc(ec2, vpc_id)
    if not sn:
        raise RuntimeError('No subnets in default VPC.')
    return vpc_id, sn


def _authorize_ingress(ec2: Any, sg_id: str, port: int) -> None:
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': port,
                    'ToPort': port,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': f'TCP {port} (dev only)'}],
                }
            ],
        )
    except ClientError as e:
        if e.response['Error']['Code'] != 'InvalidPermission.Duplicate':
            raise


def ensure_dev_security_group(
    ec2: Any,
    *,
    vpc_id: str,
    name: str,
    description: str,
    open_ports: list[int],
) -> str:
    """Return SG ID, creating one and opening requested TCP ports from anywhere (dev only)."""
    try:
        r = ec2.create_security_group(
            GroupName=name,
            Description=description,
            VpcId=vpc_id,
        )
        sg_id = r['GroupId']
    except ClientError as e:
        if e.response['Error']['Code'] != 'InvalidGroup.Duplicate':
            raise
        r = ec2.describe_security_groups(
            Filters=[
                {'Name': 'group-name', 'Values': [name]},
                {'Name': 'vpc-id', 'Values': [vpc_id]},
            ]
        )
        groups = r.get('SecurityGroups') or []
        if not groups:
            raise
        sg_id = groups[0]['GroupId']

    for port in sorted(set(open_ports)):
        _authorize_ingress(ec2, sg_id, port)
    return sg_id

