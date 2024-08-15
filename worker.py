import logging
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager

# 로깅 설정
logging.basicConfig(level=logging.DEBUG)

# Celery 앱 및 설정
celery = Celery(
    'worker', 
    broker='pyamqp://guest:guest@43.202.57.225:26262//',
)

celery.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',   # 작업 데이터 직렬화 형식을 JSON으로 설정
    accept_content=['json'],  # JSON 형식만 허용
    result_serializer='json',  # 결과 직렬화 형식을 JSON으로 설정
    timezone='Asia/Seoul',  # 타임존을 서울로 설정
    enable_utc=True,  # UTC 사용 설정
)

class SourcePortAdapter(HTTPAdapter):
    def __init__(self, source_port, **kwargs):
        self.source_port = source_port
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            source_address=('', self.source_port)  # Bind to the source port
        )

@celery.task(bind=True)
def generate_image(self, prompt: str, prompt_id: str):
    try:
        logging.info(f"Received task to generate image with prompt: {prompt}")
        
        # 이미지 생성
        try:
            image = Image.new('RGB', (200, 100), color=(73, 109, 137))
            d = ImageDraw.Draw(image)
            d.text((10, 10), prompt, fill=(255, 255, 0))
        except Exception as img_error:
            logging.error(f"Error generating image: {img_error}")
            raise self.retry(exc=img_error, countdown=10, max_retries=3)
        
        # 이미지 데이터를 base64로 인코딩
        try:
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as encode_error:
            logging.error(f"Error encoding image to base64: {encode_error}")
            raise self.retry(exc=encode_error, countdown=10, max_retries=3)
        
        # 서버로 결과 전송
        try:
            WEB_SERVER_URL = "http://43.202.57.225:28282/upload_image"
            data = {'prompt_id': prompt_id, 'image': img_str}
            
            # 특정 포트에서 요청을 보내기 위한 설정
            session = requests.Session()
            adapter = SourcePortAdapter(source_port=27272)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            response = session.post(WEB_SERVER_URL, json=data)
        
            if response.status_code == 200:
                logging.info(f"Image uploaded successfully for prompt_id: {prompt_id}")
            else:
                logging.error(f"Failed to upload image for prompt_id: {prompt_id}, Status code: {response.status_code}")
        except Exception as post_error:
            logging.error(f"Error uploading image to server: {post_error}")
            raise self.retry(exc=post_error, countdown=10, max_retries=3)
    
    except Exception as e:
        logging.error(f"Unhandled error in generating image: {e}")
        self.update_state(state='FAILURE', meta={'exc_message': str(e)})
        raise e
