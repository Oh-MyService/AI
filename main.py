# main.py
# uvicorn main:app --reload --host 0.0.0.0 --port 27272

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from celery.result import AsyncResult
from celery_worker import generate_and_send_image, app as celery_app
import logging
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from kombu import Connection


app = FastAPI()

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://118.67.128.129:28282"],  # 서버 주소를 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드를 허용
    allow_headers=["*"],  # 모든 HTTP 헤더를 허용
)

# MySQL 데이터베이스 설정
db_config = {
    'host': '118.67.128.129',
    'port': 21212,
    'user': 'root',
    'password': 'root',  # 실제 비밀번호를 사용하세요
    'database': 'ohmyservice_database'  # 사용할 데이터베이스 이름
}

# OAuth2PasswordBearer 설정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# AIOption 모델 생성
class AIOption(BaseModel):
    width: int
    height: int
    background_color: str
    mood: str
    cfg_scale: float
    sampling_steps: int
    seed: int

class Content(BaseModel):
    positive_prompt: str
    negative_prompt: str

# PromptRequest 모델 생성
class PromptRequest(BaseModel):
    user_id: int
    prompt_id: int
    content: Content
    ai_option: AIOption

### task_id 디비 추가 ###  
def update_prompt_with_task_id(prompt_id, task_id):
    try:
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            cursor = connection.cursor()

            update_query = """
            UPDATE prompts SET task_id = %s WHERE id = %s
            """
            cursor.execute(update_query, (task_id, prompt_id))
            connection.commit()

            logging.info(f"task_id {task_id} updated successfully for prompt_id {prompt_id}")
    
    except mysql.connector.Error as e:
        logging.error(f"Error updating task_id in MySQL: {e}")
        raise e
    
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            logging.info("MySQL connection closed")

@app.post("/generate-image")
async def generate_image(request: PromptRequest):
    try:
        logging.info(f"Calling Celery task with prompt_id: {request.prompt_id}, content: {request.content}")
        
        # Celery 작업을 비동기적으로 호출
        task = generate_and_send_image.apply_async(
            args=(request.prompt_id, dict(request.content), request.user_id, dict(request.ai_option))
        )
        
        logging.info(f"Celery task started with task_id: {task.id}")

        # 데이터베이스에 task_id 업데이트
        update_prompt_with_task_id(request.prompt_id, task.id)
        
        return {"message": "Image generation started", "task_id": task.id, "prompt_id": request.prompt_id}
    
    except Exception as e:
        logging.error(f"Error generating image: {e}")
        raise HTTPException(status_code=500, detail="Failed to start image generation")


@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    queue_name = 'your_queue_name'  # 실제 큐 이름으로 변경하세요
    
    # 작업 위치를 계산하는 함수
    def get_task_position(task_id: str, queue_name: str):
        with Connection(celery_app.conf.broker_url) as conn:
            queue = conn.SimpleQueue(queue_name)
            position = 0
            for message in queue:
                if message.payload.get('id') == task_id:
                    queue.close()
                    return position
                position += 1
            queue.close()
        return None

    position = get_task_position(task_id, queue_name)
    
    # 작업 상태 및 위치 반환
    if task_result.state == 'PENDING':
        return {"status": "PENDING", "position": position}
    elif task_result.state == 'FAILURE':
        return {"status": "FAILURE", "details": str(task_result.info), "position": position}
    elif task_result.state == 'SUCCESS':
        logging.info(f"Task {task_id} completed successfully.")
        return {"status": "SUCCESS", "message": "Image generation completed"}
    else:
        return {"status": task_result.state, "position": position}