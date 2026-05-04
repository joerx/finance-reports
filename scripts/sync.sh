#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$(dirname "$SCRIPT_DIR")/.env"
PYTHON="$(which python)"

S3_ENDPOINT=""
S3_BUCKET=""

if [[ $# -ne 2 ]]; then
  echo "Usage: $(basename "$0") <db-file> <quarter>" >&2
  echo "  e.g. $(basename "$0") 2026.gnucash 2026-Q1" >&2
  exit 1
fi

DB_FILE="$1"
QUARTER="$2"

if [[ ! "$QUARTER" =~ ^[0-9]{4}-Q[1-4]$ ]]; then
  echo "Error: quarter must be in YYYY-QN format (e.g. 2026-Q1)" >&2
  exit 1
fi

S3_PREFIX="expenses"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Warn: .env file not found at $ENV_FILE" >&2
else
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

if [[ -z "${S3_ENDPOINT:-}" ]]; then
  echo "Error: S3_ENDPOINT is not set" >&2
  exit 1
fi
if [[ -z "${S3_BUCKET:-}" ]]; then
  echo "Error: S3_BUCKET is not set" >&2
  exit 1
fi

OUTDIR="$(mktemp -d)"
trap 'rm -rf "$OUTDIR"' EXIT

echo "Extracting expenses from $DB_FILE for $QUARTER ..."
"$PYTHON" "$SCRIPT_DIR/batch_export.py" --db "$DB_FILE" --quarter "$QUARTER" --outdir "$OUTDIR"

echo "Syncing to s3://$S3_BUCKET/$S3_PREFIX ..."
aws s3 sync "$OUTDIR" "s3://$S3_BUCKET/$S3_PREFIX" \
  --endpoint-url "$S3_ENDPOINT"

echo "Done."
