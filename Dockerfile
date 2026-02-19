# 1. Base Image: Use a lightweight Python version
FROM python:3.11-slim

# 2. Set the Working Directory inside the container
WORKDIR /app

# 3. Install System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# --- ✨ MLOPS UPGRADE: Install 'uv' ---
# uv is a Rust-based tool that resolves dependencies 100x faster than pip.
# This completely prevents the 20-minute "Dependency Hell" timeouts.
RUN pip install uv

# 4. Copy Requirements FIRST
COPY requirements.txt .

# 5. Install CPU-only PyTorch using uv (Blazing fast)
RUN uv pip install --system --no-cache torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 6. Install the rest of the Python Dependencies using uv
RUN uv pip install --system --no-cache -r requirements.txt

# 7. Copy the rest of your code
COPY . .

# 8. Create the directory for VTO uploads so the code doesn't crash
RUN mkdir -p uploaded_images

# 9. Define Environment Variables
ENV PYTHONUNBUFFERED=1

# 10. Build the FAISS Vector Database
RUN python app/rag_indexer.py

# 11. Run the Application
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}