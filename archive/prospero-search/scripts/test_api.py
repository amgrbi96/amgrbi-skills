#!/usr/bin/env python3
"""PROSPERO API test — validates the undocumented search endpoint."""

import base64
import json
import time
import urllib.request
import urllib.error

BASE = "https://www.crd.york.ac.uk/PROSPERO/api/search"


def make_token():
    return base64.b64encode(str(int(time.time() * 1000)).encode()).decode()


def post(data, headers):
    body = json.dumps(data).encode()
    req = urllib.request.Request(BASE, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, str(e)


BASE_HEADERS = {
    "Content-Type": "application/json",
}

BODY = {
    "term": "adhd",
    "page": 1,
    "nperpage": 3,
    "sort": "TI",
    "sortorder": "ASC",
    "filters": [],
    "download": False,
    "actual": "adhd",
}

passed = 0
failed = 0

def check(test_name, status, data, expect_hits=True):
    global passed, failed
    ok = status == 200
    if ok and expect_hits:
        try:
            ok = data[0]["hits"] > 0
        except (IndexError, KeyError, TypeError):
            ok = False
    if ok:
        print(f"  PASS: {test_name}")
        passed += 1
    else:
        print(f"  FAIL: {test_name} (status={status})")
        failed += 1


print("=" * 60)
print("TEST 1: Fresh timestamp token")
print("=" * 60)
h = {**BASE_HEADERS, "prospero-auth-token": make_token()}
status, data = post(BODY, h)
print(f"Status: {status}")
print(json.dumps(data, indent=2)[:1500])
check("fresh token search", status, data)

print("\n" + "=" * 60)
print("TEST 2: Missing auth token should error")
print("=" * 60)
status, data = post(BODY, BASE_HEADERS)
print(f"Status: {status}")
is_error = status == 200 and isinstance(data, dict) and data.get("status") == "error"
if is_error:
    print(f"  PASS: correctly rejected (error: {data.get('errormessage')})")
    passed += 1
else:
    print(f"  FAIL: expected error response, got data with hits")
    failed += 1

print("\n" + "=" * 60)
print("TEST 3: download=true")
print("=" * 60)
h = {**BASE_HEADERS, "prospero-auth-token": make_token()}
body_dl = {**BODY, "download": True}
status, data = post(body_dl, h)
print(f"Status: {status}")
print(json.dumps(data, indent=2)[:1500])
check("download mode", status, data)

print("\n" + "=" * 60)
print("TEST 4: With status filter (ongoing)")
print("=" * 60)
h = {**BASE_HEADERS, "prospero-auth-token": make_token()}
body_filtered = {
    **BODY,
    "filters": [{"name": "reviewstatus", "value": ["Ongoing"]}],
}
status, data = post(body_filtered, h)
print(f"Status: {status}")
print(json.dumps(data, indent=2)[:1500])
check("status filter", status, data)

print("\n" + "=" * 60)
print("TEST 5: Multiple filters (ongoing + Clinical)")
print("=" * 60)
h = {**BASE_HEADERS, "prospero-auth-token": make_token()}
body_multi = {
    **BODY,
    "filters": [
        {"name": "reviewstatus", "value": ["Ongoing"]},
        {"name": "recordtype", "value": ["Clinical"]},
    ],
}
status, data = post(body_multi, h)
print(f"Status: {status}")
print(json.dumps(data, indent=2)[:1500])
check("multi-filter", status, data)

print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} tests")
print("=" * 60)
