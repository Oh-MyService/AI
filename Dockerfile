# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project code into the container
COPY . .

# Expose the port for outgoing requests
EXPOSE 27272

# Start the Celery worker
CMD ["celery", "-A", "worker", "worker", "--loglevel=debug", "--logfile=/var/log/celery.log", "--concurrency=1", "-Q", "default"]

