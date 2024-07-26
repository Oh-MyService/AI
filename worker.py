import redis
import json
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests

celery = Celery('tasks', broker='redis://43.202.57.225:26262/0')
redis_client = redis.Redis(host='43.202.57.225', port=26262, db=0)

WEB_SERVER_URL = "http://43.202.57.225:28282"  # 웹서버의 IP 주소 또는 호스트명으로 변경

@celery.task
def generate_image(prompt: str, task_id: str):
    task_data = {"prompt": prompt, "task_id": task_id, "status": "processing"}
    redis_client.set(task_id, json.dumps(task_data))
    
    # 이미지 생성 (여기서는 간단한 텍스트를 포함한 이미지를 만듦)
    image = Image.new('RGB', (200, 100), color = (73, 109, 137))
    d = ImageDraw.Draw(image)
    d.text((10,10), prompt, fill=(255,255,0))
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    # 웹서버로 이미지 전송
    requests.post(f"{WEB_SERVER_URL}/save-image/", json={"task_id": task_id, "image_data": img_str})

def image_worker():
    while True:
        _, message = redis_client.blpop("image_queue")
        task_data = json.loads(message)
        generate_image.delay(task_data["prompt"], task_data["task_id"])

if __name__ == "__main__":
    image_worker()
