
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --default-timeout=120 --retries=10 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "Backend.wsgi:application", "--bind", "0.0.0.0:8000"]
