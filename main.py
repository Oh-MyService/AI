from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult
from celery_app import generate_and_send_image, app as celery_app

app = FastAPI()

class ImageRequest(BaseModel):
    image_data: str

@app.post("/generate-image/")
async def generate_image(request: ImageRequest):
    # Celery task 호출
    task = generate_and_send_image.delay(request.image_data)
    return {"task_id": task.id}

@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    if task_result.state == 'PENDING':
        return {"status": "PENDING"}
    elif task_result.state == 'FAILURE':
        return {"status": "FAILURE", "details": str(task_result.info)}
    else:
        return {"status": task_result.state, "result": task_result.result}
