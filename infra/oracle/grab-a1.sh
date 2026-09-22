#!/usr/bin/env bash
# Keep asking Oracle for a free ARM (A1) VM until London has capacity.
# This tenancy may use 2 A1 cores in AD-1 and AD-3 (AD-2's limit is 0), and both
# small AMD VMs are taken (ReBind, YoLa), so A1 is the only free option left.
# "Out of host capacity" is Oracle being full, not a config error: we wait and retry.
#
#   infra/oracle/grab-a1.sh            # 1 OCPU / 6 GB (easier to get; plenty for Charge)
#   OCPUS=2 MEM=12 infra/oracle/grab-a1.sh
set -uo pipefail
cd "$(dirname "$0")"
OCPUS="${OCPUS:-1}"; MEM="${MEM:-6}"; WAIT="${WAIT:-90}"
LOG="$(mktemp)"
try=0
while :; do
  for ad in 0 2; do
    try=$((try + 1))
    printf '%s  try %d  AD-%d  %s OCPU / %s GB … ' "$(date +%H:%M:%S)" "$try" "$((ad + 1))" "$OCPUS" "$MEM"
    if terraform apply -auto-approve -input=false -no-color \
         -var ad_index="$ad" -var ocpus="$OCPUS" -var memory_gbs="$MEM" >"$LOG" 2>&1; then
      echo "got it!"
      terraform output
      command -v osascript >/dev/null && osascript -e 'display notification "Charge VM is up" with title "Oracle"'
      exit 0
    fi
    if grep -qi "out of host capacity\|InternalError\|TooManyRequests" "$LOG"; then
      echo "Oracle is full"
    else
      echo "failed for another reason:"; grep -m5 -E 'Error|error' "$LOG"; exit 1
    fi
  done
  sleep "$WAIT"
done
