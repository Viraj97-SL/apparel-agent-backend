# 1. Base Image: Use a lightweight Python version (Industry Standard)
FROM python:3.11-slim

# 2. Set the "Working Directory" inside the container
WORKDIR /app

# 3. Install System Dependencies
# Some Python packages (like faiss) need basic C++ tools.
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy Requirements FIRST (Caching Strategy)
COPY requirements.txt .

# --- SPEED BOOST: Install CPU-only PyTorch FIRST ---
# This prevents downloading the huge GPU version, saving time and space.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 5. Install the rest of the Python Dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your code
COPY . .

# 7. Create the directory for VTO uploads so the code doesn't crash
RUN mkdir -p uploaded_images

# 8. Define Environment Variables
ENV PYTHONUNBUFFERED=1

# --- 9. NEW: Build the FAISS Vector Database ---
# This generates the faiss_index folder inside the container before it starts,
# fixing the 'NoneType' ainvoke error.
RUN python app/rag_indexer.py

# 10. Run the Application
# Using shell format so ${PORT} expands correctly on Railway
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}