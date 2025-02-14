import os
import asyncio
import logging
from typing import Optional
import boto3
from cachetools import TTLCache
from concurrent.futures import ThreadPoolExecutor
from utils.session_strategy import AWSSessionStrategy, SSOSessionStrategy, IAMRoleSessionStrategy

class AWSSessionManager:
    DEFAULT_REGION = 'ap-northeast-2'

    def __init__(self, strategy: AWSSessionStrategy, max_workers: int = 10):
        self.logger = logging.getLogger(__name__)
        self.strategy = strategy
        self._session_cache = TTLCache(maxsize=100, ttl=8 * 3600)  # 8시간 캐시
        self._cache_lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    @classmethod
    def create(cls, environment: str, **kwargs) -> 'AWSSessionManager':
        """환경에 따른 세션 매니저 생성"""
        if environment.lower() == 'development':
            strategy = SSOSessionStrategy(
                sso_profile=kwargs.get('sso_profile', 'default'),
                default_region=cls.DEFAULT_REGION
            )
        else:
            strategy = IAMRoleSessionStrategy(
                role_name=kwargs.get('role_name', 'mgmt-db-monitoring-assumerole'),
                default_region=cls.DEFAULT_REGION
            )
        return cls(strategy=strategy)

    async def get_session(self, account_id: str) -> Optional[boto3.Session]:
        """계정별 AWS 세션 조회 또는 생성"""
        cache_key = f"{account_id}"

        # 캐시된 세션 확인
        async with self._cache_lock:
            if cache_key in self._session_cache:
                return self._session_cache[cache_key]

        try:
            # 세션 생성
            session = await self.strategy.create_session(account_id)
            if not session:
                return None

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
                return session.client(
                    service_name,
                    region_name=region
                )

            client = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                create_client
            )

            # 클라이언트 테스트 (RDS의 경우)
            if service_name == 'rds':
                def test_client():
                    try:
                        client.describe_db_instances(MaxRecords=20)
                    except client.exceptions.DBInstanceNotFound:
                        pass
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    test_client
                )

            return client

        except Exception as e:
            self.logger.error(
                f"Error creating {service_name} client in {region} "
                f"for account {account_id}: {e}"
            )
            return None

    async def validate_access(self) -> bool:
        """접근 권한 검증"""
        return await self.strategy.validate_access()

    def clear_cache(self):
        """세션 캐시 초기화"""
        with self._cache_lock:
            self._session_cache.clear()