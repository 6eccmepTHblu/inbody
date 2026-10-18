FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY parse_inbody.py app.py ./
COPY web web
ENV INBODY_HOST=0.0.0.0 INBODY_PDFS=/data INBODY_AUTH=1 PYTHONUNBUFFERED=1
CMD ["python", "app.py"]
