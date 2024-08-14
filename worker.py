import json
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests

# RabbitMQ 설정
celery = Celery('tasks', broker='pyamqp://guest@43.202.57.225:26262//')

WEB_SERVER_URL = "http://43.202.57.225:28282"  # 웹서버의 IP 주소 또는 호스트명으로 변경

@celery.task
def generate_image(prompt: str, prompt_id: str):
    task_data = {"prompt": prompt, "prompt_id": prompt_id}

    # 이미지 생성 (여기서는 간단한 텍스트를 포함한 이미지를 만듦)
    image = Image.new('RGB', (200, 100), color=(73, 109, 137))
    d = ImageDraw.Draw(image)
    d.text((10, 10), prompt, fill=(255, 255, 0))
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    # 웹서버로 이미지 전송
    requests.post(f"{WEB_SERVER_URL}/save-image/", json={"prompt_id": prompt_id, "image_data": img_str})

def image_worker():
    while True:
        # Celery를 사용하여 작업을 대기 및 처리
        pass  # 실제 구현에 따라 이 부분을 수정
