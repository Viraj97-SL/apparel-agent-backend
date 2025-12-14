# 1. Base Image: Use a lightweight Python version (Industry Standard)
FROM python:3.11-slim

# 2. Set the "Working Directory" inside the container
# This is like doing 'cd /app' inside the box.
WORKDIR /app

# 3. Install System Dependencies
# Some Python packages (like faiss) need basic C++ tools.
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy Requirements FIRST (Caching Strategy)
# Docker caches steps. If you change code but not requirements,
# it skips installing pip packages again. Speed boost!
COPY requirements.txt .

# 5. Install Python Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your code
COPY . .

# 7. Define Environment Variables
# This ensures Python prints logs immediately to the console.
ENV PYTHONUNBUFFERED=1

# ... (previous lines)

COPY . .

# [NEW LINE] Create the directory for VTO uploads so the code doesn't crash
RUN mkdir -p uploaded_images

ENV PYTHONUNBUFFERED=1

CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}

# 8. Run the Application
# We use shell format to allow the $PORT variable (injected by Cloud Providers)
# Host 0.0.0.0 allows external access (required for containers).
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}