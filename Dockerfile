# Use a lightweight, official Python runtime as the base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements first for better caching
COPY src/requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src/ .

# Make main.py executable (it's in the current directory now)
RUN chmod +x main.py

# Set environment variables for the Batch job
ENV AWS_REGION=us-east-1
ENV PYTHONUNBUFFERED=1

# Run the script when the container launches
CMD ["python3", "main.py"]