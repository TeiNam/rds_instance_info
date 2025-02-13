# Python 3.13 기반 이미지 사용
FROM python:3.13.1-slim

# 타임존 설정을 위한 패키지 설치 및 한국 시간대 설정
# 불필요한 패키지와 캐시 제거를 통한 이미지 최적화
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime \
    && echo "Asia/Seoul" > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 파이썬 패키지 설치를 위한 requirements.txt 복사
COPY requirements.txt .

# 패키지 설치 및 캐시 제거를 통한 최적화
RUN pip install --no-cache-dir -r requirements.txt \
    && find /usr/local/lib/python3.9/site-packages -name "*.pyc" -delete \
    && find /usr/local/lib/python3.9/site-packages -name "__pycache__" -exec rm -r {} + \
    && rm -rf ~/.cache/pip/*

# 소스 코드 복사
COPY . .

# 환경 변수 설정
ENV PYTHONPATH=/app \
    TZ=Asia/Seoul \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 보안을 위한 비특권 사용자 생성 및 권한 설정
RUN useradd -m -s /bin/bash app_user \
    && chown -R app_user:app_user /app

# 비특권 사용자로 전환
USER app_user

# 컨테이너 실행 명령
CMD ["python", "-m", "collectors.rds_instance_info_collector"]