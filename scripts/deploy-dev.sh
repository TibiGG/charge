#!/usr/bin/env bash
# Deploy the frontend to charge-bupa-dev.vercel.app (the work-in-progress site).
# charge-bupa.vercel.app (the hackathon demo) is never touched by this script: the
# project is picked by id here, not by frontend/.vercel, which still points at the demo.
set -euo pipefail
export VERCEL_ORG_ID=ciKJeIwMcIgzSgGVFAfRKjFN
export VERCEL_PROJECT_ID=prj_5BbcfNaRswLQMVIKUcQ9EsKXbU4w
cd "$(dirname "$0")/../frontend"
vercel deploy --prod --yes
