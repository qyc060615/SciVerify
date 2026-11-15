"""Regression tests for CORS preflight and origin resolution."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


class TestCorsConfiguration:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_localhost_5174_preflight(self) -> None:
        response = self.client.options(
            "/api/verification/analyze",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5174"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_127_0_0_1_5174_preflight(self) -> None:
        response = self.client.options(
            "/api/verification/analyze",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5174"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_localhost_5173_preflight(self) -> None:
        response = self.client.options(
            "/api/verification/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_unauthorized_origin_rejected(self) -> None:
        response = self.client.options(
            "/api/verification/analyze",
            headers={
                "Origin": "http://malicious-site.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.headers.get("access-control-allow-origin") != "http://malicious-site.com"

    def test_post_with_cors_headers(self) -> None:
        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "test claim", "doi": "invalid-doi"},
            headers={"Origin": "http://localhost:5174"},
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5174"
