# Dockerfile for Flask app
FROM python:3.11-slim

# set working directory
WORKDIR /app

# install build deps then python deps
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# copy application
COPY . /app

# expose Flask default port
EXPOSE 5000

# Use gunicorn for production-like server; fall back to flask if not available
ENV FLASK_APP=app.py
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
