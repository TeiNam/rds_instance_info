from abc import ABC, abstractmethod
import boto3
import logging
from typing import Optional
from botocore.exceptions import ClientError


class AWSSessionStrategy(ABC):
    """AWS 세션 생성을 위한 추상 전략 클래스"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    async def create_session(self, account_id: str) -> Optional[boto3.Session]:
        """AWS 세션 생성"""
        pass

    @abstractmethod
    async def validate_access(self) -> bool:
        """접근 권한 검증"""
        pass


class SSOSessionStrategy(AWSSessionStrategy):
    """SSO 기반 세션 생성 전략"""

    def __init__(self, sso_profile: str, default_region: str):
        super().__init__()
        self.sso_profile = sso_profile
        self.default_region = default_region

    async def create_session(self, account_id: str) -> Optional[boto3.Session]:
        try:
            profile_name = f"AdministratorAccess-{account_id}"
            return boto3.Session(
                profile_name=profile_name,
                region_name=self.default_region
            )
        except Exception as e:
            self.logger.error(f"Failed to create SSO session for account {account_id}: {e}")
            return None

    async def validate_access(self) -> bool:
        try:
            profile_account_id = self.sso_profile.split('AdministratorAccess-')[-1]
            session = await self.create_session(profile_account_id)
            if not session:
                return False

            sts = session.client('sts')
            sts.get_caller_identity()
            return True
        except Exception as e:
            self.logger.error(f"SSO validation failed: {e}")
            return False


class IAMRoleSessionStrategy(AWSSessionStrategy):
    """EC2 IAM Role 기반 세션 생성 전략"""

    def __init__(self, role_name: str, default_region: str):
        super().__init__()
        self.role_name = role_name
        self.default_region = default_region
        self._base_session = boto3.Session(region_name=default_region)

    async def create_session(self, account_id: str) -> Optional[boto3.Session]:
        try:
            sts = self._base_session.client('sts')
            role_arn = f"arn:aws:iam::{account_id}:role/{self.role_name}"

            # Role 수임
            response = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"monitoring-{account_id}"
            )

            # 임시 자격 증명으로 새 세션 생성
            credentials = response['Credentials']
            return boto3.Session(
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken'],
                region_name=self.default_region
            )
        except Exception as e:
            self.logger.error(f"Failed to assume role for account {account_id}: {e}")
            return None

    async def validate_access(self) -> bool:
        try:
            sts = self._base_session.client('sts')
            sts.get_caller_identity()
            return True
        except Exception as e:
            self.logger.error(f"IAM role validation failed: {e}")
            return False