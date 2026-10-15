"""Check a fresh local deployment through actual HTTP, without real accounts."""

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check(base: str):
    def read(path,expected=200,headers=None):
        request=Request(base+path,headers=headers or {})
        try:
            with urlopen(request,timeout=3) as response:
                status,body=response.status,response.read()
        except HTTPError as error:
            status,body=error.code,error.read()
        assert status==expected,f"{path}: expected {expected}, got {status}"
        return body

    for attempt in range(30):
        try:
            health=json.loads(read("/api/health"))
            break
        except (URLError,ConnectionError):
            if attempt==29:
                raise
            time.sleep(0.5)
    assert health["status"]=="ok"
    assert not health["media_ready"],"Fresh images should not bundle downloaded media."
    assert b'home-title' in read("/")
    assert b'owner-password' in read("/manage")
    assert not json.loads(read("/api/admin/status"))["signed_in"]
    read("/api/admin/config",401)
    read("/api/home/personal",401)
    read("/data/vault.key",404)
    read("/api/health",400,{"Host":"untrusted.example"})
    print("PASS: fresh deployment, loopback manager, owner authentication, host guard, private data, and source-only image.")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:18765")
    args=parser.parse_args()
    check(args.url.rstrip("/"))
