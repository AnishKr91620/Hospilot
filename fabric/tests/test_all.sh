#!/usr/bin/env bash
# Live endpoint test for Hospilot-Fabric @ http://192.46.212.81:8001
# Reads are safe. Writes are skipped by default — pass --write to enable.
# Usage:
#   bash scripts/test_all.sh
#   bash scripts/test_all.sh --write
#   FABRIC_API_KEY=<key> bash scripts/test_all.sh

set -euo pipefail

BASE="${FABRIC_BASE_URL:-http://192.46.212.81:8001}"
KEY="${FABRIC_API_KEY:-}"
WRITE=false
[[ "${1:-}" == "--write" ]] && WRITE=true

AUTH_HDR=()
[[ -n "$KEY" ]] && AUTH_HDR=(-H "Authorization: Bearer $KEY")

PASS=0; FAIL=0; SKIP=0

hit() {
  local method="$1" path="$2"
  local code
  code=$(curl -s -o /tmp/fab_resp -w "%{http_code}" "${AUTH_HDR[@]}" -X "$method" "${BASE}${path}")
  if [[ "$code" -lt 400 ]]; then
    echo "  PASS  $method $path  ($code)"
    PASS=$((PASS+1))
  else
    echo "  FAIL  $method $path  ($code) $(cat /tmp/fab_resp | head -c 120)"
    FAIL=$((FAIL+1))
  fi
}

hit_post() {
  local path="$1" body="${2:-}"
  local code
  code=$(curl -s -o /tmp/fab_resp -w "%{http_code}" "${AUTH_HDR[@]}" -X POST -H "Content-Type: application/json" -d "$body" "${BASE}${path}")
  if [[ "$code" -lt 400 ]]; then
    echo "  PASS  POST $path  ($code)"
    PASS=$((PASS+1))
  else
    echo "  FAIL  POST $path  ($code) $(cat /tmp/fab_resp | head -c 120)"
    FAIL=$((FAIL+1))
  fi
}

skip() {
  echo "  SKIP  $*  (writes disabled)"
  SKIP=$((SKIP+1))
}

echo ""
echo "▶ Fabric endpoint test  base=$BASE  auth=${KEY:+on}${KEY:-off}  writes=$WRITE"
echo ""

# ── health ──────────────────────────────────────────────────────────────────
hit GET /health

# ── beds ────────────────────────────────────────────────────────────────────
hit GET /beds
hit GET /beds/available-icu
hit GET /beds/dirty
hit GET /beds/dirty-icu
hit GET /beds/postop
hit GET /beds/summary

# Prime bed_id from /beds
BED_ID=$(curl -s "${AUTH_HDR[@]}" "${BASE}/beds" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)
[[ -n "$BED_ID" ]] && hit GET "/beds/$BED_ID"

# ── admissions ──────────────────────────────────────────────────────────────
hit GET /admissions/icu
hit GET /admissions/non-icu
hit GET /admissions/with-wards
hit GET /admissions/discharge-eligible
hit GET /admissions/discharge-ready
hit GET /admissions/discharge-ready-count
hit GET "/admissions/discharge-horizon?hours=24"

# Prime adm_id + patient_token from /admissions/icu
ICU=$(curl -s "${AUTH_HDR[@]}" "${BASE}/admissions/icu" 2>/dev/null || echo "[]")
ADM_ID=$(echo "$ICU" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)
PATIENT=$(echo "$ICU" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0].get('patient_token','') if d else '')" 2>/dev/null || true)

[[ -n "$ADM_ID" ]] && hit GET "/admissions/$ADM_ID"

# ── vitals ──────────────────────────────────────────────────────────────────
hit GET /vitals/critical
[[ -n "$PATIENT" ]] && hit GET "/vitals/latest?patient=$PATIENT" || { echo "  SKIP  GET /vitals/latest  (no patient token)"; SKIP=$((SKIP+1)); }

# ── ER / visits ─────────────────────────────────────────────────────────────
hit GET /visits/er
hit GET /visits/untriaged
hit GET /er/pressure

# Prime visit_id from /visits/er
VISITS=$(curl -s "${AUTH_HDR[@]}" "${BASE}/visits/er" 2>/dev/null || echo "[]")
VISIT_ID=$(echo "$VISITS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)
[[ -z "$PATIENT" ]] && PATIENT=$(echo "$VISITS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0].get('patient_token','') if d else '')" 2>/dev/null || true)

# ── tasks ────────────────────────────────────────────────────────────────────
hit GET /tasks/incomplete
hit GET /tasks/overdue
[[ -n "$ADM_ID" ]] && { hit GET "/tasks?admission=$ADM_ID"; hit GET "/tasks/completed-count?admission=$ADM_ID"; } \
  || { echo "  SKIP  GET /tasks?admission=  (no adm_id)"; echo "  SKIP  GET /tasks/completed-count  (no adm_id)"; SKIP=$((SKIP+2)); }

# ── labs ─────────────────────────────────────────────────────────────────────
hit GET /labs/orders/pending
[[ -n "$PATIENT" ]] && hit GET "/labs/results?patient=$PATIENT" || { echo "  SKIP  GET /labs/results  (no patient token)"; SKIP=$((SKIP+1)); }

# ── departments / patients ────────────────────────────────────────────────────
hit GET /departments
hit GET /patients/tokens
[[ -n "$PATIENT" ]] && hit GET "/patients?ids=$PATIENT"

# ── financial reads ───────────────────────────────────────────────────────────
hit GET /financial/invoices
hit GET "/financial/invoices?payment_status=Unpaid,Partial"
[[ -n "$PATIENT" ]] && hit GET "/financial/invoices?patient=$PATIENT"

hit GET /financial/claims
hit GET /financial/payments
hit GET /financial/refunds
hit GET /financial/contracts
hit GET /financial/collections/$(date +%Y-%m-%d)
hit GET /financial/reconciliation/$(date +%Y-%m-%d)

# Prime financial sub-resource IDs
CLAIM_ID=$(curl -s "${AUTH_HDR[@]}" "${BASE}/financial/claims" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)
PAYMENT_ID=$(curl -s "${AUTH_HDR[@]}" "${BASE}/financial/payments" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)
CONTRACT_ID=$(curl -s "${AUTH_HDR[@]}" "${BASE}/financial/contracts" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)
INVOICE_ID=$(curl -s "${AUTH_HDR[@]}" "${BASE}/financial/invoices" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')" 2>/dev/null || true)

[[ -n "$CLAIM_ID"   ]] && { hit GET "/financial/claims/$CLAIM_ID/line-items"; hit GET "/financial/claims/$CLAIM_ID/history"; hit GET "/financial/claims/$CLAIM_ID/queries"; }
[[ -n "$PAYMENT_ID" ]] && hit GET "/financial/payments/$PAYMENT_ID/entries"
[[ -n "$CONTRACT_ID" ]] && hit GET "/financial/contracts/$CONTRACT_ID/rates"
[[ -n "$INVOICE_ID" ]] && hit GET "/financial/invoices/$INVOICE_ID/line-items"

# ── writes (opt-in) ───────────────────────────────────────────────────────────
if $WRITE; then
  echo ""
  echo "  ! writes enabled — these flow through to the DB"
  [[ -n "$VISIT_ID" ]]  && hit_post "/visits/$VISIT_ID/triage"          '{"score":3}'          || skip "POST /visits/{id}/triage (no visit_id)"
  [[ -n "$ADM_ID"   ]]  && hit_post "/admissions/$ADM_ID/discharge-ready" '{"ready":false}'    || skip "POST /admissions/{id}/discharge-ready (no adm_id)"
  [[ -n "$BED_ID"   ]]  && hit_post "/beds/$BED_ID/status"              '{"status":"available"}' || skip "POST /beds/{id}/status (no bed_id)"
else
  skip "POST /visits/{id}/triage            (use --write)"
  skip "POST /admissions/{id}/discharge-ready (use --write)"
  skip "POST /admissions/transfer-pending   (use --write)"
  skip "POST /vitals/{id}/critical          (use --write)"
  skip "POST /beds/{id}/status              (use --write)"
  skip "POST /discharge-summaries/{id}/ai-note (use --write)"
fi

echo ""
echo "  $PASS passed · $FAIL failed · $SKIP skipped"
echo ""
[[ "$FAIL" -eq 0 ]]
