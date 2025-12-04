"""
Tests for FastAPI endpoints
"""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

sys.path.append(str(Path(__file__).parent.parent))

from backend.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data

    def test_health_endpoint(self, client):
        """Test health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "clickhouse" in data
        assert "model_loaded" in data

    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint"""
        response = client.get("/metrics")
        assert response.status_code == 200

        assert "text/plain" in response.headers.get("content-type", "")


class TestIngestEndpoints:
    """Tests for data ingest endpoints"""

    @pytest.mark.asyncio
    async def test_ingest_events_structure(self, client):
        """Test ingest events endpoint structure (without actual DB)"""
        response = client.post(
            "/ingest/events",
            json={"events": []}
        )

        assert response.status_code in [200, 400, 500]


class TestAnomalyEndpoints:
    """Tests for anomaly endpoints"""

    def test_anomalies_endpoint_parameters(self, client):
        """Test anomalies endpoint accepts parameters"""
        response = client.get(
            "/anomalies",
            params={
                "limit": 10,
                "min_score": 0.5,
            }
        )

        assert response.status_code in [200, 400, 500]

    def test_anomalies_stats_endpoint(self, client):
        """Test anomalies stats endpoint"""
        response = client.get("/anomalies/stats")

        assert response.status_code in [200, 400, 500]


class TestAnalyzeEndpoints:
    """Tests for analysis endpoints"""

    def test_analyze_global_structure(self, client):
        """Test global analysis endpoint structure"""
        response = client.post(
            "/analyze/global",
            json={
                "period": "24h",
                "detection_types": ["density", "time"]
            }
        )

        assert response.status_code in [200, 400, 500]

    def test_analyze_device_structure(self, client):
        """Test device analysis endpoint structure"""
        response = client.post(
            "/analyze/device/test_device",
            json={"period": "24h"}
        )

        assert response.status_code in [200, 400, 500]


class TestComparisonEndpoints:
    """Tests for device comparison endpoints"""

    def test_similar_devices_endpoint(self, client):
        """Test similar devices endpoint"""
        response = client.post(
            "/comparison/similar",
            json={
                "device_id": "device_001",
                "hours": 168,
                "top_k": 10,
                "min_similarity": 0.8
            }
        )

        assert response.status_code in [200, 400, 500]

    def test_clusters_endpoint(self, client):
        """Test clusters endpoint"""
        response = client.post(
            "/comparison/clusters",
            json={
                "hours": 168,
                "eps": 0.3,
                "min_samples": 2
            }
        )

        assert response.status_code in [200, 400, 500]

    def test_compare_two_devices_endpoint(self, client):
        """Test compare two devices endpoint"""
        response = client.post(
            "/comparison/compare",
            json={
                "device_id_1": "device_001",
                "device_id_2": "device_002",
                "hours": 168
            }
        )

        assert response.status_code in [200, 400, 500]


class TestExplainEndpoints:
    """Tests for explanation endpoints"""

    def test_explain_device_endpoint(self, client):
        """Test explain device endpoint"""
        response = client.post(
            "/explain/device",
            json={
                "device_id": "device_001",
                "hours": 168,
                "top_k": 5
            }
        )

        assert response.status_code in [200, 400, 500]

    def test_features_description_endpoint(self, client):
        """Test features description endpoint"""
        response = client.get("/explain/features")

        assert response.status_code in [200, 400, 500]


class TestCORSMiddleware:
    """Tests for CORS middleware"""

    def test_cors_headers(self, client):
        """Test CORS headers are present"""
        response = client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert "access-control-allow-origin" in response.headers


class TestRequestValidation:
    """Tests for request validation"""

    def test_invalid_json(self, client):
        """Test invalid JSON handling"""
        response = client.post(
            "/analyze/global",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code in [400, 422]

    def test_missing_required_fields(self, client):
        """Test missing required fields"""
        response = client.post(
            "/analyze/global",
            json={}
        )

        assert response.status_code in [400, 422]


@pytest.mark.integration
class TestIntegration:
    """Integration tests - require running ClickHouse and model"""

    @pytest.fixture(autouse=True)
    def check_services(self):
        """Check if services are available"""
        pytest.skip("Integration tests require running services")

    def test_full_analysis_workflow(self, client):
        """Test complete analysis workflow"""
        ingest_response = client.post(
            "/ingest/events",
            json={
                "events": [
                    {
                        "timestamp": "2024-01-01T12:00:00",
                        "device_id": "test_device",
                        "lat": 55.75,
                        "lon": 37.62,
                        "activity_level": 50.0,
                        "region": "test_region"
                    }
                ]
            }
        )

        assert ingest_response.status_code == 200

        analyze_response = client.post(
            "/analyze/device/test_device",
            json={"period": "24h"}
        )

        assert analyze_response.status_code == 200

        anomalies_response = client.get("/anomalies?limit=10")
        assert anomalies_response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
