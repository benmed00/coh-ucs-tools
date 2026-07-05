FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV UCS_API_KEY=""
ENV SQLITE_PATH=/data/app.db
ENV UCS_WEBAPP_UPLOADS=/data/uploads

RUN mkdir -p /data/uploads /data/uploads/files /data/uploads/versions /data/uploads/generated

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
