# FROM python:3.11-slim

# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1

# WORKDIR /app

# RUN apt-get update && apt-get install -y \
#     ffmpeg \
#     git \
#     curl \
#     build-essential \
#     nodejs \
#     npm \
#     && rm -rf /var/lib/apt/lists/*

# COPY Requirements.txt .



# RUN pip install --upgrade pip setuptools wheel

# RUN pip install --no-cache-dir -r Requirements.txt

# COPY . .

# EXPOSE 8000

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]



FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install native system binary compilation dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Optimize Docker cache layers by handling dependencies first
COPY Requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r Requirements.txt

# Copy application files
COPY . .

# Ensure standard operational volume paths exist locally inside the runtime workspace
RUN mkdir -p downloads temp_uploads && chmod -R 777 downloads temp_uploads

EXPOSE 8000

# Base default container execution behavior (Overridden by docker-compose for the worker service)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]