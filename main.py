from fastapi import FastAPI, BackgroundTasks, HTTPException
from celery.result import AsyncResult
from pydantic import BaseModel
from celery_app import create_image_task

app = FastAPI()

class ImageRequest(BaseModel):
    text: str

@app.post("/generate-image/")
def generate_image(request: ImageRequest, background_tasks: BackgroundTasks):
    task = create_image_task.delay(request.text)
    background_tasks.add_task(check_task_status, task.id)
    return {"task_id": task.id, "status": "Processing"}

@app.get("/result/{task_id}")
def get_result(task_id: str):
    task_result = AsyncResult(task_id)
    if task_result.state == 'SUCCESS':
        return {"task_id": task_id, "status": task_result.state, "result": task_result.result}
    elif task_result.state == 'FAILURE':
        raise HTTPException(status_code=400, detail="Task failed")
    else:
        return {"task_id": task_id, "status": task_result.state}

def check_task_status(task_id: str):
    task_result = AsyncResult(task_id)
    # 여기에 추가적인 로직을 넣을 수 있습니다. 예를 들어, 결과를 데이터베이스에 저장하거나 알림을 보내는 등의 작업.
