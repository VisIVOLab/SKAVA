class SKAVAError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: list[dict] | dict | str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidQueryError(SKAVAError):
    status_code = 400
    code = "invalid_query"


class DatasetNotFoundError(SKAVAError):
    status_code = 404
    code = "dataset_not_found"


class NoAvailableNodesError(SKAVAError):
    status_code = 503
    code = "no_available_nodes"


class ServiceUnavailableError(SKAVAError):
    status_code = 503
    code = "service_unavailable"


class BackendExecutionError(SKAVAError):
    """A node's co-located VisIVO backend was reachable but failed the cutout."""

    status_code = 502
    code = "backend_execution_failed"
