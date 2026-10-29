# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
def test_full_discovery_to_access_flow(client):
    discover = client.get("/discovery/search", params={"obs_id": "dataset-3"})
    assert discover.status_code == 200
    payload = discover.json()["results"]
    assert len(payload) == 1

    result = payload[0]
    assert result["metadata"]["obs_id"] == "dataset-3"
    assert result["best_node"] in {"A", "B"}

    access = client.get("/access/dataset-3")
    assert access.status_code == 200
    access_body = access.json()
    assert access_body["obs_id"] == "dataset-3"
    assert access_body["best_node"] in {r["code"] for r in result["replicas"]}


def test_ranking_prefers_node_b_for_dataset_3(client):
    resp = client.get("/discovery/dataset/dataset-3")
    assert resp.status_code == 200
    assert resp.json()["best_node"] == "B"
