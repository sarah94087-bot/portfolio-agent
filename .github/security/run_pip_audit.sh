#!/usr/bin/env bash
# Audits the backend's runtime dependencies with the exceptions in pip-audit-ignore.txt
# (ADR-0019). An exception needs a reason and an end date at most 90 days away; once the date
# passes it stops applying, so the finding turns red again until someone looks at it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
today="$(date -u +%F)"
limit="$(date -u -d '+90 days' +%F)"
args=()

while read -r id until reason || [[ -n "${id:-}" ]]; do
  [[ -z "${id:-}" || "$id" == \#* ]] && continue
  if [[ ! "${until:-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || ! date -d "$until" >/dev/null 2>&1; then
    echo "::error::pip-audit-ignore.txt: $id needs an end date as YYYY-MM-DD"
    exit 2
  fi
  if [[ -z "${reason:-}" ]]; then
    echo "::error::pip-audit-ignore.txt: $id needs a reason"
    exit 2
  fi
  if [[ "$until" > "$limit" ]]; then
    echo "::error::pip-audit-ignore.txt: $id ends on $until, more than 90 days away"
    exit 2
  fi
  if [[ "$until" < "$today" ]]; then
    echo "::warning::pip-audit-ignore.txt: the exception for $id ended on $until"
    continue
  fi
  echo "Ignoring $id until $until: $reason"
  args+=(--ignore-vuln "$id")
done < "$here/pip-audit-ignore.txt"

# --strict: a dependency that cannot be collected fails the audit instead of being skipped.
pip-audit "$here/../../backend" --strict --progress-spinner off "${args[@]}"
