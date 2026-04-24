from __future__ import annotations

import argparse
import os
import sys

from botocore.exceptions import ClientError

from infra.ec2 import deploy_ec2_instance
from infra.models import ProvisionConfig


def _parse_ports(value: str) -> list[int]:
    ports: list[int] = []
    for raw in value.split(','):
        token = raw.strip()
        if not token:
            continue
        port = int(token)
        if port < 1 or port > 65535:
            raise argparse.ArgumentTypeError(f'Invalid port: {port}')
        ports.append(port)
    if not ports:
        raise argparse.ArgumentTypeError('Pass at least one valid port.')
    return ports


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Provision EC2 infrastructure on AWS (boto3).')
    p.add_argument('--region', default=None, help='AWS region (default: AWS_DEFAULT_REGION or us-east-1)')
    p.add_argument('--key-name', required=True, help='EC2 key pair name (must exist in the region)')
    p.add_argument('--instance-type', default='t3.micro', help='Instance type (default: t3.micro)')
    p.add_argument('--name', default='infra-ec2', help='Value for the Name tag')
    p.add_argument('--subnet-id', default=None, help='Subnet ID (required if --security-group-id is set)')
    p.add_argument(
        '--security-group-id',
        action='append',
        dest='security_group_ids',
        help='Security group ID (repeatable). If omitted, use --create-dev-security-group.',
    )
    p.add_argument('--ami-id', default=None, help='Override AMI (default: latest AL2023 x86_64 via SSM)')
    p.add_argument(
        '--create-dev-security-group',
        action='store_true',
        help='Create a temporary SG opening selected ports from 0.0.0.0/0 (dev only).',
    )
    p.add_argument(
        '--open-ports',
        type=_parse_ports,
        default=[22],
        help='Comma-separated TCP ports for dev SG mode (default: 22). Example: 22,80,443',
    )
    p.add_argument('--user-data-file', default=None, help='Path to cloud-init/user-data file')
    p.add_argument('--wait-running', action='store_true', help='Wait until instance state is running')
    p.add_argument('--allocate-eip', action='store_true', help='Allocate and associate a new Elastic IP')
    p.add_argument('--dry-run', action='store_true', help='Validate permissions without creating resources')
    return p.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> int:
    if args.security_group_ids and args.create_dev_security_group:
        print('error: use either --security-group-id or --create-dev-security-group, not both.', file=sys.stderr)
        return 1
    if not args.security_group_ids and not args.create_dev_security_group:
        print(
            'error: pass --create-dev-security-group or --security-group-id (with --subnet-id).',
            file=sys.stderr,
        )
        return 1
    if args.security_group_ids and not args.subnet_id:
        print('error: --subnet-id is required when using --security-group-id.', file=sys.stderr)
        return 1
    return 0


def _to_config(args: argparse.Namespace) -> ProvisionConfig:
    region = args.region or os.environ.get('AWS_DEFAULT_REGION') or 'us-east-1'
    return ProvisionConfig(
        region=region,
        key_name=args.key_name,
        instance_type=args.instance_type,
        name_tag=args.name,
        subnet_id=args.subnet_id,
        security_group_ids=args.security_group_ids,
        ami_id=args.ami_id,
        create_dev_security_group=args.create_dev_security_group,
        open_ports=args.open_ports,
        user_data=args.user_data_file,
        wait_running=args.wait_running,
        allocate_eip=args.allocate_eip,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rc = _validate_args(args)
    if rc:
        return rc

    try:
        out = deploy_ec2_instance(_to_config(args))
    except (ClientError, RuntimeError, ValueError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 1

    print('Provisioned instance:')
    for k, v in out.items():
        print(f'  {k}: {v}')

    public_ip = out.get('ElasticIp') or out.get('PublicIpAddress')
    if public_ip:
        print(f'\nSSH: ssh -i <path-to-private-key> ec2-user@{public_ip}')
    return 0

