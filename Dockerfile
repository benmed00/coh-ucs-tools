FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

# Copy remaining repo files (static assets ship via package; docs/scripts optional)
COPY . .

ENV UCS_API_KEY=""
ENV SQLITE_PATH=/data/app.db
ENV UCS_WEBAPP_UPLOADS=/data/uploads

RUN mkdir -p /data/uploads /data/uploads/files /data/uploads/versions /data/uploads/generated

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "coh_ucs_tools.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
