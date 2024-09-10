#celery_worker.py
#celery -A celery_worker worker --loglevel=info -P solo

import os
import logging
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import torch
from diffusers import DiffusionPipeline
from diffusers.models.lora import LoRACompatibleConv
from celery import Celery
import json
from typing import Optional 

# 로깅 설정
logging.basicConfig(level=logging.INFO)

logging.info(f"Is torch.cuda is available? : {torch.cuda.is_available()}")

if torch.cuda.is_available():
    logging.info(f"GPU is available. Using {torch.cuda.get_device_name(0)}")
else:
    logging.info("GPU is not available, using CPU instead.")

# 로컬에서 실행 중인 RabbitMQ를 브로커로 설정
app = Celery('tasks')
app.conf.broker_url = "amqp://user:password@rabbitmq:5672//"
app.conf.broker_connection_retry_on_startup = True
app.conf.broker_heartbeat = 600
app.conf.broker_connection_timeout = 600  # 연결 시간 초과를 늘림
app.conf.task_acks_late = False
app.conf.task_reject_on_worker_lost = True
app.conf.worker_cancel_long_running_tasks_on_connection_loss=True


# MySQL 데이터베이스 설정
db_config = {
    'host': '43.202.57.225',
    'port': 21212,
    'user': 'root',
    'password': 'root',  # 실제 비밀번호를 사용하세요
    'database': 'ohmyservice_database'  # 사용할 데이터베이스 이름
}

# Init pipeline

# 모델 로드
model_name = "stabilityai/sdxl-turbo"
pipeline = DiffusionPipeline.from_pretrained(
    model_name, 
    torch_dtype=torch.float16,  # float16 사용으로 GPU 메모리 효율화
    variant="fp16"  # 16-bit floating point 사용
).to('cuda')

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

@app.task(bind=True, max_retries=0)
def generate_and_send_image(self, prompt_id, image_data, user_id, options):
    try:
        logging.info(f"Received prompt_id: ({type(prompt_id)}){prompt_id}, user_id: ({type(user_id)}){user_id}, options: {options}")

        # Set seamless tiling
        global pipeline
        pipeline = seamless_tiling(pipeline=pipeline, x_axis=True, y_axis=True)

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

            # Save image to database
            with open(image_filename, 'rb') as img_file:
                image_blob = img_file.read()
                result_id = save_image_to_database(prompt_id, user_id, image_blob)
                img_file.close()  # Ensure the file is closed before deleting
                os.remove(image_filename)

            logging.info(f"Image {i+1} saved to database with result_id: {result_id}")

        # Reset seamless tiling
        #seamless_tiling(pipeline=pipeline, x_axis=False, y_axis=False)

        torch.cuda.empty_cache()

        logging.info(f"Images and settings saved to {output_dir}")
        
        return {"message": "Images saved successfully", "result_ids": [result_id]}

    except Exception as e:
        logging.error(f"Error in generate_and_send_image: {e}")
        raise e
    
    finally:
        self.request.delivery_info['requeue'] = False

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
