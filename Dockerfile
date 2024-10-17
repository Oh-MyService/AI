# 베이스 이미지를 Python 3.12.5 slim 버전으로 설정
FROM python:3.12.5-slim

# Pillow와 같은 이미지 처리 라이브러리를 위한 필수 종속성 설치
#RUN apt-get update && apt-get install -y \
#    zlib1g-dev \
#    libjpeg-dev \
#    && apt-get clean

RUN mkdir -p /etc/pip
RUN echo "[global]\nrequire-hashes = false" > /etc/pip/pip.conf

# 작업 디렉토리 설정
WORKDIR /app

# requirements.txt 파일을 복사하고, 필요한 패키지를 설치
COPY requirements.txt .
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt

# 애플리케이션 파일을 복사
COPY . .

# 포트 설정 (FastAPI의 기본 포트 8000)
EXPOSE 8000

# 컨테이너 시작 시 FastAPI와 Celery를 동시에 실행
CMD ["celery -A celery_worker worker --loglevel=info --pool=solo"]
