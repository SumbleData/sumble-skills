# Minimal container for the zero-dependency account-scoring app.
# Stdlib-only, so no pip install. Cloud Run / fly.io set $PORT; the app reads
# $PORT and $HOST (must bind 0.0.0.0 to be reachable in a container). Basic auth
# activates in the container via BASIC_AUTH_PASS (set as a deploy secret).
FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV HOST=0.0.0.0
CMD ["python", "app.py"]
