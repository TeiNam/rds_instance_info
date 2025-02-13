import os
import asyncio
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError, TokenRetrievalError
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor


class AWSSSOSessionManager:
    DEFAULT_REGION = 'ap-northeast-2'

    def __init__(self, sso_profile: str, max_workers: int = 10):
        self.logger = logging.getLogger(__name__)
        self.sso_profile = sso_profile
        self._session_cache = TTLCache(maxsize=100, ttl=8 * 3600)  # 8시간 캐시
        self._cache_lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def get_session(self, account_id: str) -> Optional[boto3.Session]:
        """계정별 AWS 세션 조회 또는 생성"""
        cache_key = f"{account_id}"

        # 캐시된 세션 확인
        async with self._cache_lock:
            if cache_key in self._session_cache:
                return self._session_cache[cache_key]

        try:
            # 프로필 이름 구성
            profile_name = f"AdministratorAccess-{account_id}"

            # 세션 생성
            session = boto3.Session(
                profile_name=profile_name,
                region_name=self.DEFAULT_REGION
            )

            # 세션 유효성 검사
            def validate_session():
                sts = session.client('sts')
                return sts.get_caller_identity()

            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                validate_session
            )

            # 유효한 세션 캐시
            async with self._cache_lock:
                self._session_cache[cache_key] = session

            return session

        except Exception as e:
            self.logger.error(f"Failed to create session for account {account_id}: {e}")
            return None

    async def get_client(self, account_id: str, service_name: str, region: str) -> Optional[boto3.client]:
        """AWS 서비스 클라이언트 생성"""
        try:
            session = await self.get_session(account_id)
            if not session:
                return None

            def create_client():
                client = session.client(
                    service_name,
                    region_name=region
                )

                # RDS 클라이언트인 경우 간단한 API 호출로 테스트
                if service_name == 'rds':
                    try:
                        client.describe_db_instances(MaxRecords=20)
                    except client.exceptions.DBInstanceNotFound:
                        pass  # 인스턴스가 없는 것은 정상

                return client

            return await asyncio.get_event_loop().run_in_executor(
                self.executor,
                create_client
            )

        except Exception as e:
            self.logger.error(
                f"Error creating {service_name} client in {region} "
                f"for account {account_id}: {e}"
            )
            return None

    async def check_account_access(self, account_id: str) -> bool:
        """계정 접근 권한 확인"""
        try:
            session = await self.get_session(account_id)
            if not session:
                return False

            def check_access():
                sts = session.client('sts')
                return sts.get_caller_identity()

            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                check_access
            )

            return True

        except Exception as e:
            self.logger.error(f"Access check failed for account {account_id}: {e}")
            return False

    async def validate_sso_access(self) -> bool:
        """SSO 접근 권한 검증"""
        try:
            profile_account_id = self.sso_profile.split('AdministratorAccess-')[-1]
            session = await self.get_session(profile_account_id)
            if not session:
                return False

            sts = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: session.client('sts')
            )

            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: sts.get_caller_identity()
            )

            return True

        except Exception as e:
            self.logger.error(f"SSO validation failed: {e}")
            return False

    def clear_cache(self):
        """세션 캐시 초기화"""
        with self._cache_lock:
            self._session_cache.clear()