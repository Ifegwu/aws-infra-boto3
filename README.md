# aws-infra-boto3

Deploy a single EC2 instance with `boto3` using a modular infrastructure CLI.

Provisioning can either:
- use your existing subnet and security group(s), or
- create a temporary **dev** security group (selected ports open to `0.0.0.0/0`) in the default VPC.

## Project structure

The code is now modularized:

- `boto.py` - thin CLI entrypoint
- `infra/cli.py` - argument parsing and validation
- `infra/models.py` - provisioning config model
- `infra/ami.py` - AMI resolution via SSM
- `infra/network.py` - VPC/subnet and security-group logic
- `infra/ec2.py` - EC2 launch workflow and optional post-launch steps

## What the provisioner does

- Resolves an AMI:
  - default: latest Amazon Linux 2023 x86_64 from SSM parameter store
  - optional override: `--ami-id`
- Validates network/security-group inputs.
- Optionally creates a dev security group and opens configurable TCP ports.
- Launches exactly one EC2 instance with a `Name` tag.
- Supports optional user data (`cloud-init`) from file.
- Supports optional wait-until-running flow.
- Supports optional Elastic IP allocation/association.
- Supports dry-run mode for IAM/permission validation.
- Prints launch output including:
  - `InstanceId`
  - `State`
  - `PrivateIpAddress`
  - `PublicIpAddress`
  - `ImageId`
  - `SubnetId`
  - `SecurityGroupIds`
  - `ElasticIp` (when `--allocate-eip` is used)

## Prerequisites

- Python environment with:
  - `boto3`
  - `botocore`
- AWS credentials configured (environment variables, `~/.aws/credentials`, or IAM role).
- IAM permissions for:
  - `ec2:RunInstances`
  - `ec2:CreateSecurityGroup`
  - `ec2:Describe*`
  - `ec2:AuthorizeSecurityGroupIngress`
  - `ec2:AllocateAddress` (if using `--allocate-eip`)
  - `ec2:AssociateAddress` (if using `--allocate-eip`)
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
- `--name`: instance `Name` tag, defaults to `infra-ec2`.
- `--ami-id`: custom AMI ID (otherwise latest AL2023 x86_64 is resolved from SSM).
- `--subnet-id`: subnet ID (required when using `--security-group-id`).
- `--security-group-id`: security group ID; repeatable for multiple groups.
- `--create-dev-security-group`: create a new SG in the VPC and open selected ports.
- `--open-ports`: comma-separated ports for dev SG mode (default: `22`).
- `--user-data-file`: path to cloud-init/user-data script.
- `--wait-running`: wait for instance to enter `running` state.
- `--allocate-eip`: allocate and attach a new Elastic IP.
- `--dry-run`: validate permissions without creating resources.

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

### 5) Dev SG with multiple ports + wait + Elastic IP

```bash
python boto.py \
  --key-name my-key \
  --create-dev-security-group \
  --open-ports 22,80,443 \
  --wait-running \
  --allocate-eip
```

### 6) Launch with cloud-init user data

```bash
python boto.py \
  --key-name my-key \
  --create-dev-security-group \
  --user-data-file ./cloud-init.yaml
```

## Notes

- If your account/region has no default VPC, use `--subnet-id` and `--security-group-id`.
- The dev security group mode is for quick testing only; lock SSH CIDR down for production.
