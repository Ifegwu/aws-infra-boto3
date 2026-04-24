from __future__ import annotations

from typing import Any

# Latest Amazon Linux 2023 x86_64 (kernel-default), per-region SSM parameter
AL2023_X86_SSM = '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64'


def get_al2023_ami_id(ssm: Any) -> str:
    resp = ssm.get_parameters(Names=[AL2023_X86_SSM])
    params = resp.get('Parameters') or []
    if not params:
        region = ssm.meta.region_name
        raise RuntimeError(f'SSM returned no AMI for {AL2023_X86_SSM} in {region}')
    return params[0]['Value']

