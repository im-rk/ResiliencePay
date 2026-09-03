import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(name, method, path, **kwargs):
    print(f"Testing {name} ({method} {path})...")
    url = f"{BASE_URL}{path}"
    try:
        response = requests.request(method, url, **kwargs)
        if response.status_code in (200, 202):
            print(f"  [OK] {response.status_code}")
        else:
            print(f"  [FAIL] Status: {response.status_code}, Body: {response.text[:200]}")
    except Exception as e:
        print(f"  [ERROR] {e}")

if __name__ == "__main__":
    print("--- Starting API E2E Test ---")
    
    # 1. Health Checks
    test_endpoint("Health Check Root", "GET", "/")
    test_endpoint("Health Check /health", "GET", "/health")
    
    # 2. Admin (Fault Injection)
    # Using the fixed path /admin/fault-injection
    headers = {"x-admin-secret": os.environ.get("ADMIN_SECRET", "hackathon_secret")}
    test_endpoint("Admin Fault Injection", "POST", "/admin/fault-injection", headers=headers, json={"enabled": True, "rate": 0.5})
    # Reset fault injection
    test_endpoint("Admin Fault Injection Reset", "POST", "/admin/fault-injection", headers=headers, json={"enabled": False, "rate": 0.0})
    
    # 3. Batch
    test_endpoint("Batch Simulation", "POST", "/v1/pipeline/run-batch", json={"n_events": 10, "policy": "baseline", "random_seed": 42})
    
    # 4. Metrics
    test_endpoint("Metrics Summary", "GET", "/v1/metrics/summary?run_id=run_demo_bandit")
    test_endpoint("Metrics Learning Curve", "GET", "/v1/metrics/learning-curve?run_id=run_demo_bandit&bucket_size=10")
    
    # 5. Simulations
    test_endpoint("Simulations Run", "POST", "/v1/simulations/run")
    test_endpoint("Simulations Chaos", "POST", "/v1/simulations/chaos")
    test_endpoint("Simulations Bandit Stats", "GET", "/v1/simulations/bandit-stats?cause_category=insufficient_funds")
    
    # 6. Audit
    test_endpoint("Audit Trail", "GET", "/v1/audit-trail")
    
    print("--- Finished API E2E Test ---")
