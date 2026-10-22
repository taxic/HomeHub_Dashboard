#!/usr/bin/env bash
# Example: report a backup result to HomeLab Command Centre.
# Reporting is status-tracking only; this script does not run, move or delete any backup.
#
# Usage: report-backup.sh <job-id> success|failed ["message"] [backup|restore_test]
# Needs: HOMELAB_URL (e.g. http://100.101.102.103:8741) and HOMELAB_API_KEY (Settings -> Security).
set -euo pipefail
job="${1:?job id}"; status="${2:?success|failed}"; msg="${3:-}"; kind="${4:-backup}"
: "${HOMELAB_URL:?set HOMELAB_URL}"; : "${HOMELAB_API_KEY:?set HOMELAB_API_KEY}"
payload=$(python3 -c 'import json,sys; print(json.dumps({"status":sys.argv[1],"message":sys.argv[2][:500] or None,"kind":sys.argv[3]}))' "$status" "$msg" "$kind")
curl -fsS -X POST "$HOMELAB_URL/api/v1/backups/$job/report" \
  -H "Authorization: Bearer $HOMELAB_API_KEY" -H 'Content-Type: application/json' -d "$payload" >/dev/null
echo "reported $kind $status for job $job"
