FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi==0.115.6 "uvicorn[standard]==0.34.0"
COPY app.py /app/app.py
WORKDIR /app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
