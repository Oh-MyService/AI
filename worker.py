import json
import logging
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# RabbitMQ 설정
celery = Celery('tasks', broker='pyamqp://guest@43.202.57.225:26262//')

WEB_SERVER_URL = "http://43.202.57.225:28282"  # 웹서버의 IP 주소 또는 호스트명으로 변경

@celery.task
def generate_image(prompt: str, prompt_id: str):
    try:
        logging.info(f"Received task to generate image with prompt: {prompt}")
        
        # 이미지 생성
        image = Image.new('RGB', (200, 100), color=(73, 109, 137))
        d = ImageDraw.Draw(image)
        d.text((10, 10), prompt, fill=(255, 255, 0))
        
        # 이미지 데이터를 base64로 인코딩
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # 서버로 결과 전송
        data = {'prompt_id': prompt_id, 'image': img_str}
        response = requests.post(f"{WEB_SERVER_URL}/upload_image", json=data)
        
        if response.status_code == 200:
            logging.info(f"Image uploaded successfully for prompt_id: {prompt_id}")
        else:
            logging.error(f"Failed to upload image for prompt_id: {prompt_id}, Status code: {response.status_code}")
    
    except Exception as e:
        logging.error(f"Error in generating image: {e}")
        raise e
