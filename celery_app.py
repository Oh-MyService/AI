import os
import requests
from celery import Celery
from PIL import Image, ImageDraw
from io import BytesIO

app = Celery('tasks', broker=os.getenv('CELERY_BROKER_URL'), backend=os.getenv('CELERY_RESULT_BACKEND'))

@app.task
def generate_and_send_image(image_data):
    # 이미지 생성 로직
    image = generate_image(image_data)
    
    # 이미지를 메모리에 저장
    image_io = BytesIO()
    image.save(image_io, format="PNG")
    image_io.seek(0)

    # 이미지를 POST 요청으로 전송
    result_url = os.getenv('RESULT_POST_URL')
    if result_url:
        files = {'file': ('image.png', image_io, 'image/png')}
        response = requests.post(result_url, files=files)
        response.raise_for_status()

    return "Image sent successfully"

def generate_image(data):
    # 간단한 이미지 생성 예시
    image = Image.new('RGB', (100, 100), color='blue')
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), data, fill='white')
    return image
