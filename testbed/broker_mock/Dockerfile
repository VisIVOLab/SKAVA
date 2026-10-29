# The Computing Broker stand-in of the testbed. Build context: the repository root.
FROM python:3.11-slim
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.27" "httpx>=0.27"
COPY testbed/broker_mock /srv/broker_mock
WORKDIR /srv
EXPOSE 8000
CMD ["uvicorn", "broker_mock.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
