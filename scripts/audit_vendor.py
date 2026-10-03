"""Query OSV for every vendored JS package, including files outside npm's tree."""

import json
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    manifest = json.loads(Path("app/web/static/vendor/manifest.json").read_text())
    packages = sorted({(item["package"], item["version"]) for item in manifest.values()})
    payload = {
        "queries": [
            {"package": {"name": name, "ecosystem": "npm"}, "version": version}
            for name, version in packages
        ]
    }
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        results = json.load(response)["results"]
    if len(results) != len(packages):
        raise RuntimeError("Incomplete OSV response")
    vulnerable = False
    for (name, version), result in zip(packages, results, strict=True):
        ids = [v["id"] for v in result.get("vulns", [])]
        print(f"{name}@{version}: {', '.join(ids) if ids else 'no known advisories'}")
        vulnerable |= bool(ids)
    return int(vulnerable)


if __name__ == "__main__":
    sys.exit(main())
