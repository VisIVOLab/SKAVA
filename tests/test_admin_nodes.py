# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the Nodes admin CRUD UI."""
from __future__ import annotations

import re


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert m, "no csrf_token in page"
    return m.group(1)


def test_nodes_list_renders(admin_client):
    r = admin_client.get("/admin/nodes/")
    assert r.status_code == 200
    assert "Nodes" in r.text


def test_node_create_round_trip(admin_client):
    # GET the form to capture CSRF.
    r = admin_client.get("/admin/nodes/new")
    assert r.status_code == 200
    csrf = _csrf(r.text)
    # Submit the form.
    r = admin_client.post(
        "/admin/nodes/new",
        data={
            "code": "TESTNODE",
            "name": "Test Node",
            "base_url": "https://test-node.example.org",
            "is_enabled": "1",
            "is_available": "1",
            "latency_score": "10",
            "load_score": "0.1",
            "capability_score": "1.0",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text[:300]
    # The new node should appear in the list.
    r = admin_client.get("/admin/nodes/")
    assert "TESTNODE" in r.text
