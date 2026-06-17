import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings


class FederationService:
    def sources(self) -> list[dict[str, Any]]:
        return [{"base_url": url, "status": "configured"} for url in settings.federated_sources]

    def search(self, params: dict[str, Any]) -> dict[str, Any]:
        remote_results = []
        for source in settings.federated_sources:
            query = urlencode({key: value for key, value in params.items() if value is not None})
            url = f"{source}/discovery/search"
            if query:
                url = f"{url}?{query}"
            try:
                req = Request(url, headers={"Accept": "application/json"})
                with urlopen(req, timeout=settings.federation_timeout_seconds) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                remote_results.append({"source": source, "status": "ok", "response": payload})
            except Exception as exc:
                remote_results.append({"source": source, "status": "error", "error": str(exc)})

        return {"sources": self.sources(), "remote_results": remote_results}
