# Federation API

`GET /federation/search` and `GET /federation/sources`: the local catalogue
and the configured sibling SKAVA instances, asked together and merged.

SRCNet has one catalogue per site. A search that should cover the federation
is sent to any one instance, which answers from its own catalogue and asks
every sibling in ``SKAVA_FEDERATED_SRC_URLS`` (comma-separated base URLs)
concurrently (up to eight at a time), each at its own `/discovery/search`, with an HTTP timeout of
``SKAVA_FEDERATION_TIMEOUT_SECONDS`` (default 2). A sibling's own catalogue
is asked, never its fan-out, so two instances that list each other do not
loop.

## Authentication

Both endpoints follow the instance's own token rule (open unless tokens
are configured). The caller's bearer token (from `Authorization: Bearer`
or `X-SKAVA-Access-Token`) is forwarded to the siblings as it was presented
(`Authorization: Bearer`). SRCNet's IAM is one, so a token the first instance
accepted is valid at the others; an instance that requires no token passes
the token it was given along, unverified, for the siblings that do. A sibling
that refuses it (HTTP 401 or 403) is reported as `unauthorized` and the
search goes on without it. The token is never stored or returned. See [Authentication](auth.md).

## Merge

The answers are merged on the logical dataset identity, `obs_id`:

* the local catalogue's results come first, in its order, each with
  `source: "local"`;
* a sibling's result for a dataset already listed is not repeated: the sibling
  is added to that result's `also_at`, with the sibling's own `best_node`,
  `access_url` and replica count;
* a dataset only a sibling has is appended with that sibling's base URL as
  its `source`;
* the merged list is cut at `limit` (local results first).

The ranking stays each site's own: a site ranks the replicas it holds with
the telemetry it has, and the merged answer does not re-rank across sites. A
client that wants the decision of a particular site resolves the dataset's
DataLink there.

## Request

```bash
curl -s "https://skava.inaf.it/federation/search?COLLECTION=wallaby&limit=50" \
    -H "Authorization: Bearer $TOKEN" | jq
```

Parameters are those of `/discovery/search` (`obs_id`, `POS`, `BAND`, `TIME`,
`COLLECTION`, `DPTYPE`, `limit`); `offset` is not supported across sites.

## Response

```json
{
  "results": [
    {
      "metadata": {"obs_id": "wallaby-ngc4636-cube", "...": "..."},
      "replicas": ["..."],
      "best_node": "INAF-CT",
      "access_url": "https://skava.inaf.it/access/wallaby-ngc4636-cube",
      "datalink_descriptor": {"...": "..."},
      "source": "local",
      "also_at": [
        {"source": "https://skava.sarao.ac.za", "best_node": "SARAO-1",
         "access_url": "https://skava.sarao.ac.za/access/wallaby-ngc4636-cube", "replicas": 2}
      ]
    }
  ],
  "returned": 1,
  "limit": 50,
  "sources": [
    {"base_url": "https://skava.inaf.it", "status": "local", "returned": 1, "total": 1, "elapsed_ms": 3.1, "error": null},
    {"base_url": "https://skava.sarao.ac.za", "status": "ok", "returned": 1, "total": 1, "elapsed_ms": 212.4, "error": null},
    {"base_url": "https://skava.aussrc.org", "status": "timeout", "returned": 0, "total": null, "elapsed_ms": 2001.0, "error": "no answer within 2 s"}
  ],
  "duplicates_merged": 1
}
```

`sources[].status` is one of `local`, `ok`, `error` (with the reason:
`HTTP 503`, a connection error, `malformed answer: ...`), `timeout` or
`unauthorized`. A sibling in trouble never fails the search.

The local entry's `base_url` is ``SKAVA_PUBLIC_BASE_URL``; `total` is
each catalogue's own match count, `duplicates_merged` the number of
sibling results folded into `also_at`. With no siblings configured the
search answers from the local catalogue alone.

`GET /federation/sources` lists the configured siblings, without
contacting them:

```json
{"sources": [{"base_url": "https://skava.sarao.ac.za", "status": "configured"}]}
```

## Testbed

The [testbed](../development/testbed.md) runs two instances: the first open, the second
requiring the IAM's tokens (Keycloak, audience `skava`); each lists the
other. Experiment E6 measures the
merge, the token forwarding and a sibling going down.
