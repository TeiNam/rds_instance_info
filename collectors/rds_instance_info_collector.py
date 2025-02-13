import os
import json
import asyncio
import logging
from typing import List, Dict
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
from dataclasses import dataclass
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as pytz_timezone
from utils.mongodb_connector import MongoDBConnector
from utils.aws_session_manager import AWSSSOSessionManager

logger = logging.getLogger(__name__)


@dataclass
class Config:
    aws_regions: List[str]
    aws_accounts: List[str]
    environment: str
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

        return cls(
            aws_regions=aws_regions,
            aws_accounts=aws_accounts,
            environment=environment
        )


class RDSInstanceCollector:
    def __init__(self, config: Config):
        self.config = config
        self.kst = timezone(timedelta(hours=9))
        self.aws_session_manager = AWSSSOSessionManager(
            sso_profile=os.getenv('SSO_PROFILE', 'default')
        )

    async def save_instances(self, instances: List[Dict], account_id: str):
        """수집된 인스턴스 데이터를 MongoDB에 저장 (히스토리 유지)"""
        if not instances:
            logger.info(f"No instances to save for account {account_id}")
            return

        try:
            # MongoDB 컬렉션 가져오기
            collection = await MongoDBConnector.get_collection(self.config.collection_name)

            # 현재 KST 시간
            current_time = self.get_kst_time()

            # 저장할 데이터 준비
            data = {
                'timestamp': current_time,
                'collected_at': datetime.now(timezone.utc),  # UTC 시간으로 저장 (쿼리 용이)
                'account_id': account_id,
                'total_instances': len(instances),
                'instances': instances
            }

            try:
                # 새 데이터 저장 (히스토리 유지)
                result = await collection.insert_one(data)
                if result.inserted_id:
                    logger.info(
                        f"Successfully saved {len(instances)} instances for account {account_id} at {current_time}")
                else:
                    logger.error(f"Failed to insert data for account {account_id}")

                # 인덱스 생성 (쿼리 성능 최적화)
                await collection.create_index([
                    ('account_id', 1),
                    ('collected_at', -1)
                ])
                await collection.create_index('timestamp')

            except Exception as e:
                logger.error(f"MongoDB operation failed for account {account_id}: {e}")
                raise

        except Exception as e:
            logger.error(f"Error saving to MongoDB for account {account_id}: {e}")
            raise

    async def get_instance_history(self, account_id: str, days: int = 30) -> List[Dict]:
        """특정 계정의 인스턴스 히스토리 조회"""
        try:
            collection = await MongoDBConnector.get_collection(self.config.collection_name)

            # days일 전 날짜 계산
            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            # 히스토리 데이터 조회
            cursor = collection.find({
                'account_id': account_id,
                'collected_at': {'$gte': start_date}
            }).sort('collected_at', -1)

            return await cursor.to_list(length=None)

        except Exception as e:
            logger.error(f"Error retrieving history for account {account_id}: {e}")
            raise

    def get_kst_time(self) -> str:
        """KST 시간을 문자열로 반환"""
        return datetime.now(timezone.utc).astimezone(self.kst).strftime("%Y-%m-%d %H:%M:%S KST")

    async def collect_instance_data(self, account_id: str, region: str) -> List[Dict]:
        """지정된 계정과 리전의 RDS 인스턴스 데이터 수집"""
        try:
            rds_client = await self.aws_session_manager.get_client(account_id, 'rds', region)
            if not rds_client:
                logger.error(f"Failed to create RDS client for account {account_id} in region {region}")
                return []

            try:
                # ThreadPoolExecutor를 통해 동기 API 호출
                def fetch_instances():
                    paginator = rds_client.get_paginator('describe_db_instances')
                    instances = []
                    for page in paginator.paginate():
                        instances.extend(page['DBInstances'])
                    return instances

                all_instances = await asyncio.get_event_loop().run_in_executor(
                    self.aws_session_manager.executor,
                    fetch_instances
                )

                # 인스턴스 데이터 파싱
                parsed_instances = []
                for instance in all_instances:
                    parsed_instance = self._parse_instance_data(instance, account_id, region)
                    if parsed_instance:  # None이 아닌 경우만 추가
                        parsed_instances.append(parsed_instance)

                logger.info(f"Found {len(parsed_instances)} instances in {region} for account {account_id}")
                return parsed_instances

            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']
                logger.error(f"AWS API error for account {account_id} in region {region}: {error_code} - {error_message}")
                return []

        except Exception as e:
            logger.error(f"Error collecting RDS instances in {region} for account {account_id}: {e}")
            return []

    def _parse_instance_data(self, instance: Dict, account_id: str, region: str) -> Dict:
        """인스턴스 데이터 파싱"""
        try:
            serverless_config = {}
            if instance.get('Engine', '').startswith('aurora') and instance.get('ServerlessV2ScalingConfiguration'):
                serverless_config = {
                    'MinCapacity': instance['ServerlessV2ScalingConfiguration'].get('MinCapacity'),
                    'MaxCapacity': instance['ServerlessV2ScalingConfiguration'].get('MaxCapacity')
                }

            return {
                'AccountId': account_id,
                'Region': region,
                'DBInstanceIdentifier': instance.get('DBInstanceIdentifier'),
                'DBInstanceStatus': instance.get('DBInstanceStatus'),
                'Engine': instance.get('Engine'),
                'EngineVersion': instance.get('EngineVersion'),
                'DBInstanceClass': instance.get('DBInstanceClass'),
                'MultiAZ': instance.get('MultiAZ'),
                'StorageType': instance.get('StorageType'),
                'AllocatedStorage': instance.get('AllocatedStorage'),
                'MaintenanceWindow': instance.get('PreferredMaintenanceWindow'),
                'BackupWindow': instance.get('PreferredBackupWindow'),
                'BackupRetentionPeriod': instance.get('BackupRetentionPeriod'),
                'AutoMinorVersionUpgrade': instance.get('AutoMinorVersionUpgrade'),
                'PendingModifiedValues': instance.get('PendingModifiedValues'),
                'LatestRestorableTime': instance.get('LatestRestorableTime').strftime("%Y-%m-%d %H:%M:%S KST")
                if instance.get('LatestRestorableTime') else None,
                'ServerlessConfig': serverless_config if serverless_config else None,
                'Tags': {tag['Key']: tag['Value'] for tag in instance.get('TagList', [])},
                'CollectedAt': self.get_kst_time()
            }
        except Exception as e:
            logger.error(f"Error parsing instance data: {e}")
            return {
                'AccountId': account_id,
                'Region': region,
                'Error': str(e)
            }

    async def collect_all_accounts(self):
        """모든 계정의 RDS 인스턴스 데이터 수집"""
        try:
            # SSO 접근 권한 검증
            is_valid = await self.aws_session_manager.validate_sso_access()
            if not is_valid:
                logger.error("SSO access validation failed. Please check SSO login status.")
                return

            # 계정별로 모든 리전의 데이터 수집
            account_instances = {}
            for account_id in self.config.aws_accounts:
                account_tasks = []
                for region in self.config.aws_regions:
                    task = self.collect_instance_data(account_id, region)
                    account_tasks.append(task)

                # 각 계정별로 리전 데이터 수집을 동시에 처리
                region_results = await asyncio.gather(*account_tasks, return_exceptions=True)

                # 계정별 결과 처리
                valid_instances = []
                for result in region_results:
                    if isinstance(result, list):
                        valid_instances.extend(result)
                    elif isinstance(result, Exception):
                        logger.error(f"Error collecting data for account {account_id}: {str(result)}")

                if valid_instances:
                    # 수집된 인스턴스가 있는 경우에만 저장
                    await self.save_instances(valid_instances, account_id)
                    logger.info(f"Collected {len(valid_instances)} instances for account {account_id}")
                else:
                    logger.warning(f"No instances found for account {account_id}")

            logger.info(f"Completed collection for all accounts at {self.get_kst_time()}")

        except Exception as e:
            logger.error(f"Error in collect_all_accounts: {e}")
            raise


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    config = Config.from_env()

    if not config.aws_accounts:
        raise ValueError("No AWS accounts configured. Please set AWS_ACCOUNTS in .env file")

    scheduler = AsyncIOScheduler(timezone=pytz_timezone('Asia/Seoul'))
    collector = RDSInstanceCollector(config)

    try:
        await MongoDBConnector.initialize()

        # 매일 아침 8시에 실행하는 스케줄 등록
        scheduler.add_job(
            collector.collect_all_accounts,
            trigger=CronTrigger(
                hour=8,
                minute=0,
                timezone=pytz_timezone('Asia/Seoul')
            ),
            id='rds_collector',
            name='RDS Instance Collector',
            replace_existing=True,
            misfire_grace_time=3600
        )

        scheduler.start()
        logger.info("Scheduler started. Next run will be at 08:00 KST")

        # 개발 환경에서는 즉시 실행
        if config.environment.lower() == 'development':
            logger.info("Development environment detected. Running initial collection...")
            await collector.collect_all_accounts()
            logger.info("Initial collection completed")

        # Keep the main task running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping scheduler...")

    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        logger.info("Shutting down...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await MongoDBConnector.close()
        logger.info("Cleanup completed")


if __name__ == '__main__':
    asyncio.run(main())