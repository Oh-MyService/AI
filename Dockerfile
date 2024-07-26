# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI app code into the container
COPY . .

CMD ["python", "/worker.py"]