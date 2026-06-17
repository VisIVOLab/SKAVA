FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system skava && adduser --system --ingroup skava skava

WORKDIR /srv/app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x ./docker/entrypoint.sh && chown -R skava:skava /srv/app

USER skava

CMD ["/srv/app/docker/entrypoint.sh"]
