import os
import json
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv


@dataclass
class Config:
    aws_regions: List[str]
    aws_accounts: List[str]
    environment: str
    auth_type: str  # 'sso' 또는 'iam_role'
    collection_name: str = 'aws_rds_instance_daily_info'
    role_name: str = 'mgmt-db-monitoring-assumerole'

    @classmethod
    def from_env(cls) -> 'Config':
        load_dotenv()
        aws_regions = json.loads(os.getenv('AWS_REGIONS', '[]'))
        aws_accounts_str = os.getenv('AWS_ACCOUNTS', '[]')
        environment = os.getenv('ENVIRONMENT', 'production')

        try:
            aws_accounts = json.loads(aws_accounts_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"AWS_ACCOUNTS environment variable is not a valid JSON array: {e}")

        # 환경에 따른 인증 방식 결정
        auth_type = 'sso' if environment.lower() == 'development' else 'iam_role'

        # 운영 환경에서 role_name 환경 변수 확인
        role_name = os.getenv('AWS_ROLE_NAME', 'mgmt-db-monitoring-assumerole')

        return cls(
            aws_regions=aws_regions,
            aws_accounts=aws_accounts,
            environment=environment,
            auth_type=auth_type,
            role_name=role_name
        )