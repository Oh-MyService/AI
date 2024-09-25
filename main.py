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

# OAuth2PasswordBearer 설정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# AIOption 모델 생성
class AIOption(BaseModel):
    width: int
    height: int
    background_color: str
    pattern: int
    mood: str
    cfg_scale: float
    sampling_steps: int
    seed: int

# PromptRequest 모델 생성
class PromptRequest(BaseModel):
    user_id: int
    prompt_id: int
    content: str
    ai_option: AIOption

@app.post("/generate-image")
async def generate_image(request: PromptRequest):
    try:
        logging.info(f"Calling Celery task with prompt_id: {request.prompt_id}, content: {request.content}")
        
        # Celery 작업을 비동기적으로 호출 (apply_async 사용)
        task = generate_and_send_image.apply_async(
            args=(request.prompt_id, request.content, request.user_id, dict(request.ai_option))
        )
        
        logging.info(f"Celery task started with task_id: {task.id}")
        return {"message": "Image generation started", "task_id": task.id, "prompt_id": request.prompt_id}
    
    except Exception as e:
        logging.error(f"Error generating image: {e}")
        raise HTTPException(status_code=500, detail="Failed to start image generation")

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    
    if task_result.state == 'PENDING':
        return {"status": "PENDING"}
    elif task_result.state == 'FAILURE':
        return {"status": "FAILURE", "details": str(task_result.info)}
    elif task_result.state == 'SUCCESS':
        logging.info(f"Task {task_id} completed successfully.")
        return {"status": "SUCCESS", "message": "Image generation completed"}
    else:
        return {"status": task_result.state}
