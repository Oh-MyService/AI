import logging
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests
from requests.exceptions import RequestException

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

# Celery 앱 및 설정
celery = Celery(
    'worker',
    broker='pyamqp://guest@43.202.57.225:26262//',  # RabbitMQ 브로커 설정
)

celery.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',    # 작업 데이터를 JSON으로 직렬화
    accept_content=['json'],   # JSON 형식의 데이터만 허용
    result_serializer='json',  # 결과 데이터를 JSON으로 직렬화
    timezone='Asia/Seoul',     # 타임존을 서울로 설정
    enable_utc=True,           # UTC 시간 사용
)

@celery.task(bind=True)
def generate_image(self, prompt: str, prompt_id: str):
    logging.info(f"Received task to generate image with prompt: {prompt}")
    
    # 이미지 생성
    try:
        image = Image.new('RGB', (200, 100), color=(73, 109, 137))
        draw = ImageDraw.Draw(image)
        draw.text((10, 10), prompt, fill=(255, 255, 0))
        logging.info("Image generated successfully")
    except Exception as img_error:
        logging.error(f"Error generating image: {img_error}")
        raise self.retry(exc=img_error, countdown=10, max_retries=3)
    
    # 이미지 데이터를 base64로 인코딩
    try:
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        logging.debug(f"Base64 Encoded Image: {img_str[:100]}...")  # 이미지 문자열의 일부만 로그에 출력
    except Exception as encode_error:
        logging.error(f"Error encoding image to base64: {encode_error}")
        raise self.retry(exc=encode_error, countdown=10, max_retries=3)
    
    # BE 서버로 결과 전송
    try:
        BE_SERVER_URL = "http://be-server-address:port/upload_image"  # BE 서버의 URL로 변경
        data = {'prompt_id': prompt_id, 'image': img_str}
        
        response = requests.post(BE_SERVER_URL, json=data)
    
        if response.status_code == 200:
            logging.info(f"Image uploaded successfully for prompt_id: {prompt_id}")
        else:
            logging.error(f"Failed to upload image for prompt_id: {prompt_id}, Status code: {response.status_code}")
            if response.status_code >= 500:
                raise self.retry(exc=Exception(f"HTTP error {response.status_code}"), countdown=10, max_retries=3)
    
    except RequestException as req_error:
        logging.error(f"Error uploading image to BE server: {req_error}")
        raise self.retry(exc=req_error, countdown=10, max_retries=3)
    except Exception as e:
        logging.error(f"Unhandled error during image upload: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)

    logging.info(f"Task completed successfully for prompt: {prompt_id}")
