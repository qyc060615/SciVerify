"""Explicit manual API check. Non-model probes only; no model inference."""
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app
from fastapi.testclient import TestClient

if __name__ == '__main__':
    logging.getLogger('httpx').setLevel(logging.WARNING)
    # No lifespan context: do not recover or schedule any existing jobs.
    client = TestClient(app, base_url='http://127.0.0.1:8000')
    try:
        settings = client.get('/api/settings')
        settings.raise_for_status()
        response = client.post('/api/settings/status/refresh', json={},
                               headers={'X-Settings-Token': settings.json()['management_token']})
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    finally:
        client.close()
