from celery import Celery
from PIL import Image, ImageDraw, ImageFont
import os

# RabbitMQ를 브로커로 사용하는 Celery 앱 생성
celery = Celery('tasks', broker='amqp://guest:guest@rabbitmq:5672//', backend='rpc://')

@celery.task
def create_image_task(text: str):
    img = Image.new('RGB', (200, 100), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    d.text((10, 10), text, fill=(255, 255, 0))

    # 생성된 이미지를 저장
    image_path = f"/tmp/{text}.png"
    img.save(image_path)

    return image_path
