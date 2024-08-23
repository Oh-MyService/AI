import os
import requests
from celery import Celery
from PIL import Image, ImageDraw
from io import BytesIO
import base64
import logging
import mysql.connector
from mysql.connector import Error
from datetime import datetime

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

@app.task
def generate_and_send_image(prompt_id, image_data, user_id):
    try:
        logging.info(f"Received prompt_id: ({type(prompt_id)}){prompt_id}, image_data: ({type(image_data)}){image_data}, user_id: ({type(user_id)}){user_id}")

        result_ids = []

        # 이미지를 4장 생성 및 저장
        for i in range(4):
            # 이미지 생성 로직
            image = generate_image(image_data, image_index=i+1)

            # 이미지를 메모리에 저장
            image_io = BytesIO()
            image.save(image_io, format="PNG")
            image_io.seek(0)

            # 이미지를 base64로 인코딩
            image_base64 = base64.b64encode(image_io.getvalue()).decode('utf-8')

            # 이미지 데이터를 MySQL 데이터베이스에 저장
            image_blob = base64.b64decode(image_base64)  # base64 디코딩
            result_id = save_image_to_database(prompt_id, user_id, image_blob)

            logging.info(f"Image {i+1} saved to database with result_id: {result_id}")
            result_ids.append(result_id)
        
        return {"message": "Images saved successfully", "result_ids": result_ids}

    except Exception as e:
        logging.error(f"Error in generate_and_save_image: {e}")
        raise e

def generate_image(data, image_index):
    try:
        # 간단한 이미지 생성 예시
        image = Image.new('RGB', (100, 100), color=(0, 0, 255 - 50 * image_index))  # 색상 변화를 주어 4개의 이미지 차별화
        draw = ImageDraw.Draw(image)
        draw.text((10, 10), f"{data} #{image_index}", fill='white')  # 이미지 번호 추가
        return image

    except Exception as e:
        logging.error(f"Error generating image: {e}")
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

