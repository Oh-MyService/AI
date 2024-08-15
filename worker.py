import logging
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# Celery 설정
celery = Celery('worker', broker='pyamqp://guest@43.202.57.225:26262//')
celery.conf.broker_connection_retry_on_startup = True

@celery.task
def generate_image(prompt: str, prompt_id: str):
    try:
        logging.info(f"Received task to generate image with prompt: {prompt}")
        
        # 이미지 생성
        try:
            image = Image.new('RGB', (200, 100), color=(73, 109, 137))
            d = ImageDraw.Draw(image)
            d.text((10, 10), prompt, fill=(255, 255, 0))
        except Exception as img_error:
            logging.error(f"Error generating image: {img_error}")
            raise img_error
        
        # 이미지 데이터를 base64로 인코딩
        try:
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as encode_error:
            logging.error(f"Error encoding image to base64: {encode_error}")
            raise encode_error
        
        # 서버로 결과 전송
        try:
            WEB_SERVER_URL = "http://43.202.57.225:28282/upload_image"
            data = {'prompt_id': prompt_id, 'image': img_str}
            response = requests.post(WEB_SERVER_URL, json=data)
        
            if response.status_code == 200:
                logging.info(f"Image uploaded successfully for prompt_id: {prompt_id}")
            else:
                logging.error(f"Failed to upload image for prompt_id: {prompt_id}, Status code: {response.status_code}")
        except Exception as post_error:
            logging.error(f"Error uploading image to server: {post_error}")
            raise post_error
    
    except Exception as e:
        logging.error(f"Unhandled error in generating image: {e}")
        raise e
