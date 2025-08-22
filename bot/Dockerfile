FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# -u ensures unbuffered stdout/stderr additionally
CMD ["python", "-u", "main.py"]