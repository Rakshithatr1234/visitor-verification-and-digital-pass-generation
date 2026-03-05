FROM python:3.11-slim

# Install system dependencies (Tesseract + OpenCV requirements)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxrender1 \
        libxext6 \
    && rm -rf /var/lib/apt/lists/*

# note: if builds still fail, check the Render build logs for which package caused exit 100
# and ensure the base image's apt sources are up to date; rerun the build by pushing a new commit.

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Copy the rest of the application
COPY . .

# Expose port (Render will override this)
EXPOSE 5000

# Run the app

CMD ["python", "app.py"]

