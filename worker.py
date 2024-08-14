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
    try:
        # 이미지 생성
        image = Image.new('RGB', (200, 100), color=(73, 109, 137))
        d = ImageDraw.Draw(image)
        d.text((10, 10), prompt, fill=(255, 255, 0))
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        # 웹서버로 이미지 전송
        response = requests.post(f"{WEB_SERVER_URL}/save-image/", json={"prompt_id": prompt_id, "image_data": img_str})
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
    except requests.exceptions.RequestException as e:
        print(f"Failed to send image data to the server: {e}")
        raise

# image_worker 함수는 Celery 워커로 대체되므로 필요하지 않습니다.
