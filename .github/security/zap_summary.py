"""One table of what ZAP found, for the run page. Usage: zap_summary.py <report.json>.

Fails when the report is missing, so a scan that produced nothing is never read as clean.
"""

import json
import os
import sys
from collections import Counter
from urllib.parse import urlsplit


def rows(report):
    found = {}
    paths = set()
    for site in report.get("site", []):
        for alert in site.get("alerts", []):
            key = (int(alert["riskcode"]), alert["pluginid"], alert["name"])
            found[key] = found.get(key, 0) + int(alert.get("count", 0))
            paths.update(urlsplit(i["uri"]).path for i in alert.get("instances", []))
    return sorted(found.items(), key=lambda item: (-item[0][0], item[0][1])), paths


def main(path):
    try:
        with open(path, encoding="utf-8") as f:
            found, paths = rows(json.load(f))
    except FileNotFoundError:
        print(f"::error::no ZAP report at {path}")
        return 1

    risks = {3: "High", 2: "Medium", 1: "Low", 0: "Informational"}
    by_risk = Counter(risks[risk] for (risk, _, _), _ in found)
    headline = ", ".join(f"{by_risk[r]} {r}" for r in risks.values() if by_risk[r]) or "no alerts"
    api_paths = sorted(p for p in paths if p.startswith("/api/"))

    lines = [f"{risks[risk]} | {rule} | {name} | {count}" for (risk, rule, name), count in found]
    lines.append(f"{len(paths)} paths with alerts, {len(api_paths)} under /api/ {api_paths}")

    # One annotation: the checks API serves these without a sign-in, unlike the step logs.
    message = "\n".join([headline, *lines])
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::notice title=ZAP baseline::{escaped}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### ZAP baseline: {headline}\n\n")
            f.write("| Risk | Rule | Alert | Instances |\n|---|---|---|---|\n")
            for line in lines[:-1]:
                f.write(f"| {line} |\n")
            f.write(f"\n{lines[-1]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
