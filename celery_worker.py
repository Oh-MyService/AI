#celery_worker.py
#celery -A celery_worker worker --loglevel=info -P solo

import os
import logging
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import torch
from diffusers import StableDiffusionPipeline
from diffusers.models.lora import LoRACompatibleConv
from celery import Celery
import json
from typing import Optional  # <-- Add this import

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# 로컬에서 실행 중인 RabbitMQ를 브로커로 설정
app = Celery('tasks', broker='pyamqp://guest@localhost//')

# MySQL 데이터베이스 설정
db_config = {
    'host': '43.202.57.225',
    'port': 21212,
    'user': 'root',
    'password': 'root',  # 실제 비밀번호를 사용하세요
    'database': 'ohmyservice_database'  # 사용할 데이터베이스 이름
}

# Init pipeline
model_name = "runwayml/stable-diffusion-v1-5"
pipeline = StableDiffusionPipeline.from_pretrained(model_name, torch_dtype=torch.float16, use_safetensors=True)
pipeline.enable_model_cpu_offload()

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

@app.task
def generate_and_send_image(prompt_id, image_data, user_id):
    try:
        logging.info(f"Received prompt_id: ({type(prompt_id)}){prompt_id}, user_id: ({type(user_id)}){user_id}")

        # Set seamless tiling
        global pipeline
        pipeline = seamless_tiling(pipeline=pipeline, x_axis=True, y_axis=True)

        # 임의의 값 설정
        width = 512
        height = 512
        num_inference_steps = 50
        guidance_scale = 7.5
        num_images_per_prompt = 4
        seed = 42  # 고정된 시드를 사용하여 결과를 재현 가능하게 설정
        generator = torch.Generator(device='cuda').manual_seed(seed)

        # Generate and save images with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = os.path.join(r'C:\Users\ParkChunSoo\Desktop\산학쭈고\ai_images', timestamp)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Generate images using AI model
        images = pipeline(
            prompt=[image_data],
            negative_prompt=None,  # negative prompt 없음
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            num_images_per_prompt=num_images_per_prompt,
            generator=generator
        ).images

        image_filenames = []
        for i, image in enumerate(images):
            image_filename = os.path.join(output_dir, f'image_{i+1}.png')
            image.save(image_filename)
            image_filenames.append(image_filename)

            # Save image to database
            with open(image_filename, 'rb') as img_file:
                image_blob = img_file.read()
                result_id = save_image_to_database(prompt_id, user_id, image_blob)

            logging.info(f"Image {i+1} saved to database with result_id: {result_id}")

        # Save settings to JSON
        settings = {
            'prompt': image_data,
            'negative_prompt': None,
            'width': width,
            'height': height,
            'num_inference_steps': num_inference_steps,
            'guidance_scale': guidance_scale,
            'num_images_per_prompt': num_images_per_prompt,
            'seed': seed,
            'image_filenames': image_filenames,
            'model': model_name
        }

        json_filename = os.path.join(output_dir, 'settings.json')
        with open(json_filename, 'w') as json_file:
            json.dump(settings, json_file, indent=4)

        # Reset seamless tiling
        seamless_tiling(pipeline=pipeline, x_axis=False, y_axis=False)

        torch.cuda.empty_cache()

        logging.info(f"Images and settings saved to {output_dir}")
        
        return {"message": "Images saved successfully", "result_ids": [result_id]}

    except Exception as e:
        logging.error(f"Error in generate_and_send_image: {e}")
        raise e

def save_image_to_database(prompt_id, user_id, image_blob):
    try:
        # MySQL 데이터베이스에 연결
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            cursor = connection.cursor()

            # 이미지 저장을 위한 SQL 쿼리
            insert_query = """
            INSERT INTO results (prompt_id, user_id, image_data, created_at) 
            VALUES (%s, %s, %s, %s)
            """
            # 현재 시간
            created_at = datetime.now()

            # 이미지와 프롬프트 ID를 데이터베이스에 저장
            cursor.execute(insert_query, (prompt_id, user_id, image_blob, created_at))
            connection.commit()

            # 결과 ID 반환
            result_id = cursor.lastrowid

            logging.info("Image data inserted into MySQL database successfully")

            return result_id

    except Error as e:
        logging.error(f"Error connecting to MySQL: {e}")
        raise e

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            logging.info("MySQL connection closed")
