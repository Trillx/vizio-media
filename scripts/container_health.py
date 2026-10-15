"""Loopback health check that also works when no sample media is installed."""

import json
import os
from urllib.request import urlopen


def main():
    port=int(os.getenv("VIZIO_PORT","8765"))
    with urlopen(f"http://127.0.0.1:{port}/api/health",timeout=3) as response:
        if response.status!=200 or json.load(response).get("status")!="ok":
            raise SystemExit(1)


if __name__=="__main__":
    main()
