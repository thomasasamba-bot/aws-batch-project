# Use a lightweight, official Python runtime as the base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY src/ ./src/
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make main.py executable
RUN chmod +x main.py

# Run the script when the container launches
CMD ["python3", "src/main.py"]