# Use an official Python runtime as a parent image
# FROM python:3.9-slim
# 使用镜像加速
FROM docker.m.daocloud.io/library/python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# build-essential is often needed for compiling Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Make port 34521 available to the world outside this container
EXPOSE 34521

# Run app.py when the container launches
CMD ["uvicorn", "new_report:app", "--host", "0.0.0.0", "--port", "34521"]
