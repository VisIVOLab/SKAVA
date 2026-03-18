# SKAVA Runbook

## Deploy (staging)

```bash
docker compose -f docker-compose.staging.yml up --build -d
```

## Restart

```bash
docker compose -f docker-compose.staging.yml restart skava-discovery
```

## Check Health

```bash
curl -s http://localhost:8080/availability?include_nodes=true | jq
curl -s http://localhost:8080/health/db | jq
curl -s http://localhost:8080/metrics | head
```

## Check Logs

```bash
docker compose -f docker-compose.staging.yml logs -f skava-discovery
docker compose -f docker-compose.staging.yml logs -f reverse-proxy
docker compose -f docker-compose.staging.yml logs -f postgres
```

## Common Issues

1. DB connection failures on startup
- Verify `SKAVA_DATABASE_URL`
- Check postgres health: `docker compose -f docker-compose.staging.yml ps`

2. 503 no available nodes
- Validate `nodes.is_enabled` and `nodes.is_available` flags in DB
- Check replica rows in `dataset_replicas`

3. Invalid query errors (400)
- Verify `POS` uses `CIRCLE <ra> <dec> <radius>`
- Verify `BAND` and `TIME` are numeric intervals

## DB Migration + Seed (manual)

```bash
docker compose -f docker-compose.staging.yml exec skava-discovery alembic upgrade head
docker compose -f docker-compose.staging.yml exec skava-discovery python -m app.seed
```
