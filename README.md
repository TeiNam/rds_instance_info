# RDS Instance Info Collector

AWS RDS 인스턴스의 정보를 수집하고 MongoDB에 저장하는 자동화된 수집기입니다. 여러 AWS 계정과 리전에 걸쳐 RDS 인스턴스의 상세 정보를 수집하고, 이를 시계열 데이터로 저장하여 모니터링 및 분석에 활용할 수 있습니다.

## 주요 기능

- 다중 AWS 계정 지원
- 다중 리전 데이터 수집
- AWS SSO 인증 지원
- MongoDB를 이용한 시계열 데이터 저장
- 일일 자동 수집 (매일 아침 8시)
- Serverless v2 구성 정보 수집
- 태그 정보 수집

## 프로젝트 구조

```
rds_instance_info/
├── collectors/                # 데이터 수집기 모듈
│   ├── __init__.py
│   └── rds_instance_info_collector.py
├── docker/                   # Docker 관련 파일
│   └── Dockerfile
├── utils/                    # 유틸리티 모듈
│   ├── __init__.py
│   ├── aws_session_manager.py
│   └── mongodb_connector.py
├── main.py                   # 애플리케이션 진입점
├── requirements.txt          # 프로젝트 의존성
└── README.md                 # 프로젝트 문서
```

## 필수 요구사항

- Python 3.8 이상
- MongoDB 4.0 이상
- AWS SSO 접근 권한
- 필요한 AWS IAM 권한:
  - rds:DescribeDBInstances
  - rds:ListTagsForResource

## 설치 방법

1. 프로젝트 클론
```bash
git clone [repository_url]
cd rds_instance_info
```

2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. 의존성 설치
```bash
pip install -r requirements.txt
```

## 환경 설정

1. `.env` 파일을 프로젝트 루트 디렉토리에 생성하고 다음 변수들을 설정:

```env
# AWS 설정
AWS_REGIONS='["ap-northeast-2", "ap-northeast-1"]'
AWS_ACCOUNTS='["123456789012", "987654321098"]'
SSO_PROFILE="default"

# 환경 설정
ENVIRONMENT="production"  # 또는 "development"

# MongoDB 설정
MONGODB_URI="mongodb://localhost:27017"
MONGODB_DATABASE="aws_monitoring"
```

## 실행 방법

### 일반 실행
```bash
python main.py
```

### Docker를 이용한 실행
```bash
docker build -t rds-instance-info -f docker/Dockerfile .
docker run --env-file .env rds-instance-info
```

## 수집 데이터

수집기는 다음과 같은 RDS 인스턴스 정보를 수집합니다:

- 인스턴스 식별자
- 상태
- 엔진 종류 및 버전
- 인스턴스 클래스
- 스토리지 정보
- 백업 설정
- 유지보수 기간
- 태그 정보
- Serverless v2 구성 (해당하는 경우)

## 데이터 저장 구조

MongoDB에 저장되는 데이터 구조:

```javascript
{
  "timestamp": "2024-01-01 08:00:00 KST",
  "collected_at": ISODate("2024-01-01T08:00:00Z"),
  "account_id": "123456789012",
  "total_instances": 5,
  "instances": [
    {
      "AccountId": "123456789012",
      "Region": "ap-northeast-2",
      "DBInstanceIdentifier": "database-1",
      // ... 기타 인스턴스 상세 정보
    }
    // ... 기타 인스턴스들
  ]
}
```

## 스케줄링

- 기본적으로 매일 아침 8시(KST)에 수집이 실행됩니다.
- 개발 환경(`ENVIRONMENT="development"`)에서는 시작 시 즉시 수집이 실행됩니다.

## 문제 해결

### 일반적인 문제

1. SSO 인증 실패
   - AWS SSO 로그인 상태를 확인하세요
   - SSO_PROFILE 설정을 확인하세요

2. MongoDB 연결 실패
   - MongoDB 서버 실행 상태 확인
   - MONGODB_URI 설정 확인

### 로그 확인

로그는 다음 형식으로 출력됩니다:
```
2024-01-01 08:00:00,000 - root - INFO - Starting RDS Instance Info Collector...
```

## 라이센스

[라이센스 정보 추가]

## 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request
