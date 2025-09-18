# Use a lightweight, official Python runtime as the base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY src/ ./src/
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for AWS
# (AWS credentials will be provided via IAM role)
#ENV AWS_DEFAULT_REGION=us-east-1

# Run the script when the container launches
CMD ["python3", "src/main.py"]