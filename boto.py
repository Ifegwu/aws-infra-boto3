"""Deploy an EC2 instance on AWS with boto3.

Requires AWS credentials (env, ~/.aws/credentials, or IAM role) and IAM permission
for ec2:RunInstances, ec2:CreateSecurityGroup, ec2:Describe*, ssm:GetParameters.

Example::

    uv run python -m trades.boto --key-name my-key --region eu-central-1

    # Use an existing security group and subnet (e.g. non-default VPC)::
    uv run python -m trades.boto --key-name my-key --subnet-id subnet-xxx --security-group-id sg-xxx
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Latest Amazon Linux 2023 x86_64 (kernel-default), per-region SSM parameter
AL2023_X86_SSM = '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64'


def _get_al2023_ami_id(region: str) -> str:
    ssm = boto3.client('ssm', region_name=region)
    resp = ssm.get_parameters(Names=[AL2023_X86_SSM])
    params = resp.get('Parameters') or []
    if not params:
        raise RuntimeError(f'SSM returned no AMI for {AL2023_X86_SSM} in {region}')
    return params[0]['Value']


def _default_vpc_id(ec2: Any) -> str | None:
    r = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    vpcs = r.get('Vpcs') or []
    return vpcs[0]['VpcId'] if vpcs else None


def _pick_subnet_in_vpc(ec2: Any, vpc_id: str) -> str | None:
    r = ec2.describe_subnets(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )
    subnets = r.get('Subnets') or []
    if not subnets:
        return None
    subnets.sort(key=lambda s: s['SubnetId'])
    return subnets[0]['SubnetId']


def _ensure_security_group_ssh(
    ec2: Any,
    *,
    vpc_id: str,
    name: str,
    description: str,
) -> str:
    """Return security group ID, creating one that allows TCP 22 from anywhere (dev only)."""
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
        return sg_id

    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'SSH (lock down in prod)'}],
            }
        ],
    )
    return sg_id


def deploy_ec2_instance(
    *,
    region: str,
    key_name: str,
    instance_type: str,
    name_tag: str,
    subnet_id: str | None,
    security_group_ids: list[str] | None,
    ami_id: str | None,
    create_dev_security_group: bool,
) -> dict[str, Any]:
    ec2 = boto3.client('ec2', region_name=region)
    image_id = ami_id or _get_al2023_ami_id(region)

    if security_group_ids:
        sg_ids = list(security_group_ids)
        if not subnet_id:
            raise ValueError('When using custom security groups, pass --subnet-id as well.')
        run_kw: dict[str, Any] = {
            'SubnetId': subnet_id,
            'SecurityGroupIds': sg_ids,
        }
    else:
        if subnet_id:
            sn_info = ec2.describe_subnets(SubnetIds=[subnet_id])
            subs = sn_info.get('Subnets') or []
            if not subs:
                raise RuntimeError(f'Subnet not found: {subnet_id}')
            vpc_id = subs[0]['VpcId']
            sn = subnet_id
        else:
            vpc_id = _default_vpc_id(ec2)
            if not vpc_id:
                raise RuntimeError(
                    'No default VPC in this account/region. Pass --subnet-id and --security-group-id.'
                )
            sn = _pick_subnet_in_vpc(ec2, vpc_id)
            if not sn:
                raise RuntimeError('No subnets in default VPC.')
        if create_dev_security_group:
            sg = _ensure_security_group_ssh(
                ec2,
                vpc_id=vpc_id,
                name=f'{name_tag}-ssh-dev',
                description=f'Temporary SSH for {name_tag} (dev; restrict CIDR in production)',
            )
            sg_ids = [sg]
        else:
            raise RuntimeError(
                'Pass --security-group-id or use --create-dev-security-group '
                '(opens SSH to 0.0.0.0/0).'
            )
        run_kw = {'SubnetId': sn, 'SecurityGroupIds': sg_ids}

    resp = ec2.run_instances(
        ImageId=image_id,
        MinCount=1,
        MaxCount=1,
        InstanceType=instance_type,
        KeyName=key_name,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': name_tag}],
            }
        ],
        **run_kw,
    )
    inst = resp['Instances'][0]
    return {
        'InstanceId': inst['InstanceId'],
        'State': inst['State']['Name'],
        'PrivateIpAddress': inst.get('PrivateIpAddress'),
        'ImageId': image_id,
        'SubnetId': run_kw.get('SubnetId'),
        'SecurityGroupIds': run_kw.get('SecurityGroupIds'),
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Deploy an EC2 instance on AWS (boto3).')
    p.add_argument('--region', default=None, help='AWS region (default: AWS_DEFAULT_REGION or us-east-1)')
    p.add_argument('--key-name', required=True, help='EC2 key pair name (must exist in the region)')
    p.add_argument('--instance-type', default='t3.micro', help='Instance type (default: t3.micro)')
    p.add_argument('--name', default='trades-ec2', help='Value for the Name tag')
    p.add_argument('--subnet-id', default=None, help='Subnet ID (required if --security-group-id is set)')
    p.add_argument(
        '--security-group-id',
        action='append',
        dest='security_group_ids',
        help='Security group ID (repeatable). If omitted, use --create-dev-security-group with default VPC.',
    )
    p.add_argument('--ami-id', default=None, help='Override AMI (default: latest AL2023 x86_64 via SSM)')
    p.add_argument(
        '--create-dev-security-group',
        action='store_true',
        help='Create a security group allowing SSH from 0.0.0.0/0 (dev only; use with default VPC).',
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    region = args.region or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1'

    if args.security_group_ids and args.create_dev_security_group:
        print('error: use either --security-group-id or --create-dev-security-group, not both.', file=sys.stderr)
        return 1

    if not args.security_group_ids and not args.create_dev_security_group:
        print(
            'error: pass --create-dev-security-group (default VPC) or --security-group-id (and --subnet-id).',
            file=sys.stderr,
        )
        return 1

    try:
        out = deploy_ec2_instance(
            region=region,
            key_name=args.key_name,
            instance_type=args.instance_type,
            name_tag=args.name,
            subnet_id=args.subnet_id,
            security_group_ids=args.security_group_ids,
            ami_id=args.ami_id,
            create_dev_security_group=args.create_dev_security_group,
        )
    except (ClientError, RuntimeError, ValueError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 1

    print('Launched instance:')
    for k, v in out.items():
        print(f'  {k}: {v}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
