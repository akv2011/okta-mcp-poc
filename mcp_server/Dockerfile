FROM python:3.12-slim
RUN pip install --no-cache-dir "fastmcp>=3.2,<4" httpx
COPY server.py /app/server.py
WORKDIR /app
CMD ["python", "server.py"]
