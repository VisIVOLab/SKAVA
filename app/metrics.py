from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "skava_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "skava_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)

RANKING_DECISIONS = Counter(
    "skava_ranking_decisions_total",
    "Number of ranking decisions by chosen node",
    ["node"],
)

FALLBACK_EVENTS = Counter(
    "skava_ranking_fallback_total",
    "Number of fallback events when top candidate fails",
    ["reason"],
)

DB_ERRORS = Counter(
    "skava_db_errors_total",
    "Number of database errors",
    ["operation"],
)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def record_http_request(method: str, endpoint: str, status: int, elapsed_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed_seconds)


def record_ranking_decision(node: str) -> None:
    RANKING_DECISIONS.labels(node=node).inc()


def record_fallback_event(reason: str) -> None:
    FALLBACK_EVENTS.labels(reason=reason).inc()


def record_db_error(operation: str) -> None:
    DB_ERRORS.labels(operation=operation).inc()
