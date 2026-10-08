FROM python:3.12-slim
RUN pip install --no-cache-dir "fastmcp>=4.0.11,<5" httpx
COPY server.py /app/server.py
WORKDIR /app
CMD ["python", "server.py"]
