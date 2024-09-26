import redis
import json

def get_task_progress(task_id):
    redis_client = redis.Redis(host='118.67.128.129', port=6379, db=0)
    redis_key = f"task_progress:{task_id}"
    try:
        redis_data = redis_client.get(redis_key)
        if redis_data is not None:
            data = json.loads(redis_data)
            progress = data.get('progress')
            estimated_remaining_time = data.get('estimated_remaining_time')
            print(f"현재 진행률: {progress:.2f}%")
            print(f"예상 남은 시간: {estimated_remaining_time}")
            return data
        else:
            print("진행 상황 정보를 찾을 수 없습니다.")
            return None
    except Exception as e:
        print(f"오류 발생: {e}")
        return None

# 실제 작업 ID를 입력하세요
task_id = input()
get_task_progress(task_id)
