"""Observabilidade do gateway: X-Correlation-ID, log de acesso em JSON e métricas no formato Prometheus.

- Todo pedido recebe um `X-Correlation-ID` (o do cliente, se for válido; senão um novo). Ele é repassado aos serviços
  (a api e o billing o colocam nos eventos de negócio), devolvido na resposta e escrito no log de acesso: dá para seguir
  uma requisição do gateway até a api e o billing procurando o mesmo id.
- `/metrics` só responde com `Authorization: Bearer $METRICS_TOKEN`; sem a variável o endpoint não existe (404).
"""
import json
import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

access_log = logging.getLogger("metastatistic.access")
if not access_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    access_log.addHandler(_h)
    access_log.setLevel(logging.INFO)
    access_log.propagate = False


class Metrics:
    def __init__(self):
        self.reset()

    def reset(self):
        self.requests: dict[tuple[str, str], int] = defaultdict(int)       # (classe de status, método) -> n
        self.bucket: dict[float, int] = defaultdict(int)
        self.duration_sum = 0.0
        self.duration_count = 0
        self.denied = 0                                                      # 401/403 (autenticação/autorização)

    def observe(self, method: str, status: int, seconds: float):
        self.requests[(f"{status // 100}xx", method)] += 1
        self.duration_sum += seconds
        self.duration_count += 1
        for b in BUCKETS:
            if seconds <= b:
                self.bucket[b] += 1
        if status in (401, 403):
            self.denied += 1

    def render(self) -> str:
        out = ["# HELP gateway_requests_total Requisições por classe de status e método.", "# TYPE gateway_requests_total counter"]
        for (cls, method), n in sorted(self.requests.items()):
            out.append(f'gateway_requests_total{{status="{cls}",method="{method}"}} {n}')
        out += ["# HELP gateway_denied_total Requisições recusadas (401/403).", "# TYPE gateway_denied_total counter", f"gateway_denied_total {self.denied}",
                "# HELP gateway_request_duration_seconds Latência das requisições.", "# TYPE gateway_request_duration_seconds histogram"]
        for b in BUCKETS:
            out.append(f'gateway_request_duration_seconds_bucket{{le="{b}"}} {self.bucket.get(b, 0)}')
        out += [f'gateway_request_duration_seconds_bucket{{le="+Inf"}} {self.duration_count}',
                f"gateway_request_duration_seconds_sum {self.duration_sum:.6f}", f"gateway_request_duration_seconds_count {self.duration_count}"]
        return "\n".join(out) + "\n"


metrics = Metrics()


class ObservabilityMiddleware:
    """ASGI puro: troca/insere o X-Correlation-ID nos cabeçalhos ANTES do app (o proxy os repassa) e mede a resposta."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = [(k, v) for k, v in scope["headers"] if k != b"x-correlation-id"]
        supplied = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"x-correlation-id"), "")
        cid = supplied if VALID_ID.match(supplied) else uuid.uuid4().hex
        headers.append((b"x-correlation-id", cid.encode()))
        scope = {**scope, "headers": headers}
        start, status = time.perf_counter(), 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message = {**message, "headers": [*message.get("headers", []), (b"x-correlation-id", cid.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            path = scope.get("path", "")
            if not path.startswith("/health") and path != "/metrics":
                metrics.observe(scope.get("method", "GET"), status, elapsed)
                access_log.info(json.dumps({
                    "event": "http.request", "ts": datetime.now(timezone.utc).isoformat(), "correlation_id": cid,
                    "method": scope.get("method"), "path": path, "status": status, "ms": round(elapsed * 1000, 1),
                }))
