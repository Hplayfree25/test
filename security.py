import hashlib
import hmac
import os
import threading
import time
from collections import deque
from typing import Set

class SecurityException(Exception):
    def __init__(self, message: str, status_code: int = 403, code: str = "security_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code

class RateLimiter:
    def __init__(self, max_requests: int = 180, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets = {}
        self._lock = threading.Lock()

    def check(self, identifier: str):
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(identifier, deque())
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                raise SecurityException(
                    "Too many requests. Please retry later.",
                    status_code=429,
                    code="rate_limited",
                )
            bucket.append(now)

class SecurityManager:
    def __init__(self):
        allowed_ips = os.environ.get("ALLOWED_PROXY_IPS", "")
        self.allowed_ips: Set[str] = {ip.strip() for ip in allowed_ips.split(",") if ip.strip()}
        self.signing_secret = os.environ.get("INTERNAL_SIGNING_SECRET", "")
        self.timestamp_tolerance = int(os.environ.get("SIGNATURE_TOLERANCE_SECONDS", "300"))
        max_requests = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "240"))
        window_seconds = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.rate_limiter = RateLimiter(max_requests=max_requests, window_seconds=window_seconds)
        self.require_https = os.environ.get("REQUIRE_HTTPS", "true").lower() == "true"

    def enforce(self, flask_request):
        self._enforce_https(flask_request)
        self._enforce_ip_allowlist(flask_request)
        if self.signing_secret:
            self._verify_signature(flask_request)
        client_identifier = self._derive_client_identifier(flask_request)
        self.rate_limiter.check(client_identifier)

    def _enforce_https(self, flask_request):
        scheme = flask_request.headers.get("X-Forwarded-Proto", flask_request.scheme)
        if self.require_https and scheme != "https":
            raise SecurityException("HTTPS is required for this endpoint.", code="https_required")

    def _enforce_ip_allowlist(self, flask_request):
        if not self.allowed_ips:
            return
        forwarded_for = flask_request.headers.get("X-Forwarded-For", "")
        remote_addr = flask_request.remote_addr or ""
        candidates = {ip.strip() for ip in forwarded_for.split(",") if ip.strip()}
        candidates.add(remote_addr)
        if not candidates.intersection(self.allowed_ips):
            raise SecurityException("IP address is not allowed.", code="ip_not_allowed")

    def _verify_signature(self, flask_request):
        signature = flask_request.headers.get("X-Internal-Signature")
        timestamp_header = flask_request.headers.get("X-Internal-Timestamp")
        if not signature or not timestamp_header:
            raise SecurityException("Security headers are missing.", status_code=401, code="signature_missing")
        try:
            timestamp = int(timestamp_header)
        except ValueError as exc:
            raise SecurityException("Timestamp header is invalid.", status_code=401, code="timestamp_invalid") from exc
        now = int(time.time())
        if abs(now - timestamp) > self.timestamp_tolerance:
            raise SecurityException("Timestamp is outside the allowed tolerance.", status_code=401, code="timestamp_out_of_range")
        body = flask_request.get_data(cache=True) or b""
        payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
        expected_signature = hmac.new(
            self.signing_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise SecurityException("Signature validation failed.", status_code=401, code="signature_invalid")

    def _derive_client_identifier(self, flask_request) -> str:
        authorization = flask_request.headers.get("Authorization", "").strip()
        if authorization:
            return authorization[-32:]
        forwarded_for = flask_request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return flask_request.remote_addr or "anonymous"

security_manager = SecurityManager()
