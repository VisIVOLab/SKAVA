# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
def test_smoke_core_endpoints(client):
    assert client.get("/availability").status_code == 200
    assert client.get("/health/db").status_code == 200
    assert client.get("/capabilities").status_code == 200
    assert client.get("/metrics").status_code == 200
