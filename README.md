# aws-infra-boto3

Deploy a single EC2 instance with `boto3` using a small CLI script in `boto.py`.

The script can either:
- use your existing subnet and security group(s), or
- create a temporary **dev** security group (SSH open to `0.0.0.0/0`) in the default VPC.

## What `boto.py` does

- Resolves an AMI:
  - default: latest Amazon Linux 2023 x86_64 from SSM parameter store
  - optional override: `--ami-id`
- Validates network/security-group inputs.
- Optionally creates a dev security group for SSH (`tcp/22`) if `--create-dev-security-group` is set.
- Launches exactly one EC2 instance with a `Name` tag.
- Prints launch output including:
  - `InstanceId`
  - `State`
  - `PrivateIpAddress`
  - `ImageId`
  - `SubnetId`
  - `SecurityGroupIds`

## Prerequisites

- Python environment with:
  - `boto3`
  - `botocore`
- AWS credentials configured (environment variables, `~/.aws/credentials`, or IAM role).
- IAM permissions for:
  - `ec2:RunInstances`
  - `ec2:CreateSecurityGroup`
  - `ec2:Describe*`
  - `ssm:GetParameters`
- An existing EC2 key pair in the target region (`--key-name`).

## Usage

```bash
python boto.py --key-name <your-keypair> --create-dev-security-group
```

### Required arguments

- `--key-name`: EC2 key pair name (must exist in the selected region).

### Optional arguments

- `--region`: AWS region (defaults to `AWS_DEFAULT_REGION`, then `us-east-1`).
- `--instance-type`: defaults to `t3.micro`.
- `--name`: instance `Name` tag, defaults to `trades-ec2`.
- `--ami-id`: custom AMI ID (otherwise latest AL2023 x86_64 is resolved from SSM).
- `--subnet-id`: subnet ID (required when using `--security-group-id`).
- `--security-group-id`: security group ID; repeatable for multiple groups.
- `--create-dev-security-group`: create a new SG with SSH open from anywhere (dev only).

## Validation rules

- You must choose exactly one mode:
  - `--security-group-id` (with `--subnet-id`), **or**
  - `--create-dev-security-group`
- Using both modes together returns an error.
- Using neither mode returns an error.

## Examples

### 1) Default VPC + auto-created dev security group

```bash
python boto.py \
  --key-name my-key \
  --region eu-central-1 \
  --create-dev-security-group
```

### 2) Existing subnet + existing security group

```bash
python boto.py \
  --key-name my-key \
  --region eu-central-1 \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-id sg-0123456789abcdef0
```

### 3) Multiple existing security groups

```bash
python boto.py \
  --key-name my-key \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-id sg-aaaabbbbcccc11111 \
  --security-group-id sg-ddddeeeeffff22222
```

### 4) Custom AMI

```bash
python boto.py \
  --key-name my-key \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-id sg-0123456789abcdef0 \
  --ami-id ami-0123456789abcdef0
```

## Notes

- If your account/region has no default VPC, use `--subnet-id` and `--security-group-id`.
- The dev security group mode is for quick testing only; lock SSH CIDR down for production.
