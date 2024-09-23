#celery_worker.py
#celery -A celery_worker worker --loglevel=info -P solo

import os
import logging
from minio import Minio
from minio.error import S3Error
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import torch
from diffusers import DiffusionPipeline
from diffusers.models.lora import LoRACompatibleConv
from celery import Celery
import json
from typing import Optional 

# MySQL 데이터베이스 설정
db_config = {
    'host': '43.202.57.225',
    'port': 21212,
    'user': 'root',
    'password': 'root',  # 실제 비밀번호를 사용하세요
    'database': 'ohmyservice_database'  # 사용할 데이터베이스 이름
}

# MinIO 클라이언트 설정
minio_client = Minio(
    "118.67.128.129:9000",
    access_key="minio",
    secret_key="minio1234",
    secure=False
)
bucket_name = "test"

# 로깅 설정
logging.basicConfig(level=logging.INFO)

logging.info(f"Is torch.cuda is available? : {torch.cuda.is_available()}")

if torch.cuda.is_available():
    logging.info(f"GPU is available. Using {torch.cuda.get_device_name(0)}")
else:
    logging.info("GPU is not available, using CPU instead.")

# 로컬에서 실행 중인 RabbitMQ를 브로커로 설정
app = Celery('tasks', broker='amqp://guest:guest@118.67.128.129:5672//')
app.conf.update(
    broker_connection_retry_on_startup=True,
    broker_pool_limit=None,
    task_acks_late=True,
    broker_heartbeat=None,
    worker_prefetch_multiplier=1,
)

# Init pipeline
pipeline = None

def prepare_pipeline(model_name):
    pipeline = DiffusionPipeline.from_pretrained(
        model_name, 
        torch_dtype=torch.float16,  # float16 사용으로 GPU 메모리 효율화
        variant="fp16"  # 16-bit floating point 사용
    ).to('cuda')
    return pipeline

def seamless_tiling(pipeline, x_axis, y_axis):
    def asymmetric_conv2d_convforward(self, input: torch.Tensor, weight: torch.Tensor, bias: Optional[torch.Tensor] = None):
        self.paddingX = (self._reversed_padding_repeated_twice[0], self._reversed_padding_repeated_twice[1], 0, 0)
        self.paddingY = (0, 0, self._reversed_padding_repeated_twice[2], self._reversed_padding_repeated_twice[3])
        working = torch.nn.functional.pad(input, self.paddingX, mode=x_mode)
        working = torch.nn.functional.pad(working, self.paddingY, mode=y_mode)
        return torch.nn.functional.conv2d(working, weight, bias, self.stride, torch.nn.modules.utils._pair(0), self.dilation, self.groups)

    # Set padding mode
    x_mode = 'circular' if x_axis else 'constant'
    y_mode = 'circular' if y_axis else 'constant'

    targets = [pipeline.vae, pipeline.text_encoder, pipeline.unet]
    convolution_layers = []
    for target in targets:
        for module in target.modules():
            if isinstance(module, torch.nn.Conv2d):
                convolution_layers.append(module)

    for layer in convolution_layers:
        if isinstance(layer, LoRACompatibleConv) and layer.lora_layer is None:
            layer.lora_layer = lambda * x: 0

        layer._conv_forward = asymmetric_conv2d_convforward.__get__(layer, torch.nn.Conv2d)

    return pipeline

def upload_image_to_minio(image_path, image_name):
    try:
        # 이미지 파일을 MinIO에 업로드
        minio_client.fput_object(bucket_name, image_name, image_path)
        logging.info(f"Image {image_name} uploaded to MinIO")
        
        # 이미지 URL 반환
        image_url = minio_client.presigned_get_object(bucket_name, image_name)
        return image_url
    except S3Error as e:
        logging.error(f"Error uploading image to MinIO: {e}")

@app.task(bind=True, max_retries=0, acks_late=True)
def generate_and_send_image(self, prompt_id, image_data, user_id, options):
    # set pipeline
    try:
        global pipeline
        if pipeline is None:
            pipeline = seamless_tiling(
                pipeline=prepare_pipeline("stabilityai/sdxl-turbo"), 
                x_axis=True, 
                y_axis=True
            )
            
    except Exception as e:
        logging.error(f"Error in loading pipeline: {e}")
        raise e

    # create image
    try:
        logging.info(f"Received prompt_id: ({type(prompt_id)}){prompt_id}, user_id: ({type(user_id)}){user_id}, options: {options}")

        # 임의의 값 설정
        width = options["width"]
        height = options["height"]
        num_inference_steps = options["sampling_steps"]
        guidance_scale = 7.0#float(options["cfg_scale"])
        num_images_per_prompt = 4
        seed = options["seed"]  # 고정된 시드를 사용하여 결과를 재현 가능하게 설정
        generator = torch.Generator(device='cuda').manual_seed(seed)

        pos_prompt = "seamless " + image_data + " pattern, fabric textiled pattern"
        neg_prompt = "irregular shape, deformed, asymmetrical, wavy lines, blurred, low quality,on fabric, real photo, shadow, cracked, text"

        output_dir = '.'

        # Generate images using AI model
        images = pipeline(
            prompt=pos_prompt,
            negative_prompt=neg_prompt, 
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            num_images_per_prompt=num_images_per_prompt,
            generator=generator
        ).images

        for i, image in enumerate(images):
            image_filename = os.path.join(output_dir, f'image_{i+1}.png')
            image.save(image_filename)

            # MinIO에 이미지 업로드
            image_url = upload_image_to_minio(image_filename, f'image_{i+1}.png')

            # 데이터베이스에 URL 저장
            result_id = save_image_url_to_database(prompt_id, user_id, image_url)
            logging.info(f"Image {i+1} URL saved to database with result_id: {result_id}")

            os.remove(image_filename)

            logging.info(f"Image {i+1} saved to database with result_id: {result_id}")

        torch.cuda.empty_cache()

        logging.info(f"Images and settings saved to {output_dir}")
        
        return {"message": "Images saved successfully", "result_ids": [result_id]}

    except Exception as e:
        logging.error(f"Error in generate_and_send_image: {e}")
        raise e

def save_image_url_to_database(prompt_id, user_id, image_url):
    try:
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            cursor = connection.cursor()

            insert_query = """
            INSERT INTO results (prompt_id, user_id, image_data, created_at) 
            VALUES (%s, %s, %s, %s)
            """
            created_at = datetime.now()
            cursor.execute(insert_query, (prompt_id, user_id, image_url, created_at))
            connection.commit()

            result_id = cursor.lastrowid
            logging.info("Image URL inserted into MySQL database successfully")

            return result_id

    except mysql.connector.Error as e:
        logging.error(f"Error connecting to MySQL: {e}")
        raise e

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            logging.info("MySQL connection closed")
