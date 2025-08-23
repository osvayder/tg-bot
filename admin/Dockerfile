FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]