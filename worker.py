import logging
from celery import Celery
from PIL import Image, ImageDraw
import io
import base64
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Celery app and settings
celery = Celery(
    'worker', 
    broker='pyamqp://guest:guest@43.202.57.225:26262//',
)

celery.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',   # Set the task data serialization format to JSON
    accept_content=['json'],  # Only allow JSON format
    result_serializer='json',  # Set result serialization format to JSON
    timezone='Asia/Seoul',  # Set timezone to Seoul
    enable_utc=True,  # Enable UTC
)

class SourcePortAdapter(HTTPAdapter):
    def __init__(self, source_port, **kwargs):
        self.source_port = source_port
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            source_address=('', self.source_port)  # Bind to the source port
        )

@celery.task(bind=True)
def generate_image(self, prompt: str, prompt_id: str):
    try:
        logging.info(f"Received task to generate image with prompt: {prompt}")
        
        # Image creation
        try:
            image = Image.new('RGB', (200, 100), color=(73, 109, 137))
            d = ImageDraw.Draw(image)
            d.text((10, 10), prompt, fill=(255, 255, 0))
        except Exception as img_error:
            logging.error(f"Error generating image: {img_error}")
            raise self.retry(exc=img_error, countdown=10, max_retries=3)
        
        # Encoding image to base64
        try:
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as encode_error:
            logging.error(f"Error encoding image to base64: {encode_error}")
            raise self.retry(exc=encode_error, countdown=10, max_retries=3)

        # Uploading image to server
        try:
            WEB_SERVER_URL = "http://43.202.57.225:28282/upload_image"
            data = {'prompt_id': prompt_id, 'image': img_str}

            # Setting up a session with a specific source port
            session = requests.Session()
            adapter = SourcePortAdapter(source_port=27272)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            response = session.post(WEB_SERVER_URL, json=data)

            if response.status_code == 200:
                logging.info(f"Image uploaded successfully for prompt_id: {prompt_id}")
            else:
                logging.error(f"Failed to upload image for prompt_id: {prompt_id}, Status code: {response.status_code}")
        except Exception as post_error:
            logging.error(f"Error uploading image to server: {post_error}")
            raise self.retry(exc=post_error, countdown=10, max_retries=3)

    except Exception as e:
        logging.error(f"Unhandled error in generating image: {e}")
        self.update_state(state='FAILURE', meta={'exc_message': str(e)})
        raise e
