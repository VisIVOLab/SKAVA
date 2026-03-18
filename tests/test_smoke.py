def test_smoke_core_endpoints(client):
    assert client.get("/availability").status_code == 200
    assert client.get("/health/db").status_code == 200
    assert client.get("/capabilities").status_code == 200
    assert client.get("/metrics").status_code == 200
