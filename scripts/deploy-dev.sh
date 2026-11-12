#!/usr/bin/env bash
# Deploy this checkout's frontend to charge-bupa-dev.vercel.app (the dev site) by hand.
# CI does this on every push to `dev`. charge-bupa.vercel.app (live, from `main`) is never
# touched here: the project is picked by id, not by frontend/.vercel, which points at the live one.
set -euo pipefail
export VERCEL_ORG_ID=team_6xXVIFQZ74qnbRcdqlPeYEFG  # "tibigg's projects"
export VERCEL_PROJECT_ID=prj_5BbcfNaRswLQMVIKUcQ9EsKXbU4w
cd "$(dirname "$0")/../frontend"
npx -y vercel@latest deploy --prod --yes
