# Formulari Bridge — Claude Code Context

## What this project is
A FastAPI MCP server for outpatient pharmacy drug substitution,
built for the Agents Assemble Healthcare AI Hackathon (Prompt Opinion / Darena Health).
All patient data is SYNTHETIC. No real PHI anywhere in this repo.
Submitted to Devpost. Now being polished as a portfolio piece.

## Architecture
Four-agent A2A system on Prompt Opinion platform:

Agent 0 — Clinical Classifier (BYO)
  Reads free-text clinical notes, identifies drug class need via GPT-4o.
  Only fires when doctor writes a note instead of naming a drug.
  Tool: classifyClinicalIntent_mcp

Agent A — Clinical Receptionist (Orchestrator)
  Doctor-facing interface. Coordinates all other agents.
  Calls getPharmacySummary_mcp (primary) or runFullPharmacyCheck_mcp (detailed).
  Never makes clinical decisions. Doctor always confirms.

Agent B — Hardware Sentinel (BYO)
  Inventory and data layer. Called by Agent A when needed.
  Tools: all individual MCP tools.

Agent C — Clinical Synthesiser (BYO)
  Safety reasoning layer. Ranks alternatives, explains flags in plain English.
  Never invents flags. Only explains what the rules engine returns.
  No MCP tools — reasoning only.

MCP Server (this repo): FastAPI, 11 tools, HMAC audit trail, rules engine.
Deployed: AWS Elastic Beanstalk
URL: http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com

## File structure
- main.py              — FastAPI app, all 11 MCP tools, rules engine, audit trail,
                         override store, audit dashboard
- mock_db.json         — 75 drugs, 5 synthetic FHIR patients, 3 external pharmacies
- classifier/
  - classify_intent.py     — GPT-4o classification via GitHub Models API
  - generate_training_data.py — generates training_data.json
  - training_data.json       — 25 few-shot examples for classifier
- prompts.py           — all four agent system prompts
- .platform/nginx/conf.d/  — nginx SSE configuration
- .ebextensions/       — AWS EB nginx config
- requirements.txt     — Python dependencies
- .env.example         — environment variable template

## MCP tools (11)
- getPharmacySummary_mcp        ← PRIMARY tool for Prompt Opinion (compact ~800 byte response)
- runFullPharmacyCheck_mcp      ← Full detailed response (use for REST testing)
- getHardwareInventory_mcp
- getLogisticsEstimate_mcp
- getFormularyAlternatives_mcp  ← contains contraindication flags
- getDoseVariants_mcp
- flagLowStockReplenishment_mcp ← recommendation only, never automatic
- getExternalPharmacyOptions_mcp
- getAuditTrace_mcp
- classifyClinicalIntent_mcp    ← ONLY via Agent 0 consult, never directly
- confirmDispensing_mcp         ← logs doctor's final dispensing decision

## Critical rules — DO NOT change without explicit instruction
1. Rules engine in main.py fires contraindication flags. LLM explains them.
   Never modify rules engine to delegate flag generation to an LLM.
2. HMAC_SECRET must come from environment variable — never hardcode.
3. All patient data stays synthetic. Never add real patient data.
4. No auto-approval logic anywhere — doctor always confirms every substitution.
5. mock_db.json is the single source of truth for drug and patient data.
6. classifyClinicalIntent_mcp must never be called directly by Agent A.
   It is only called when Agent A explicitly consults Clinical Classifier.
7. getPharmacySummary_mcp is the PRIMARY tool for Prompt Opinion — it returns
   compact responses that fit within SSE connection limits.
8. confirmDispensing_mcp must be called after every doctor confirmation.
   If is_override=true, override_reason is REQUIRED (400 error if missing).

## Doctor workflow (Agent A)
STEP 1: Extract drug name and patient ID from message
STEP 2: Call getPharmacySummary_mcp
STEP 3: Present results in structured clinical format with ━━━ borders
STEP 4: Handle doctor's choice:
  - No flags → call confirmDispensing_mcp directly
  - Has flags + IN STOCK → show override menu (A/B/C/D options), wait for reason
  - Has flags + OUT OF STOCK → route directly to external pharmacy, log override
  - Doctor replies 0 → go back to options list
STEP 5: Call confirmDispensing_mcp with is_override and override_reason

## Override reason codes
A → "Clinical judgment: benefit outweighs risk"
B → "Patient cleared by specialist"
C → "Flag not applicable: patient context changed"
D → "System suggestion incorrect: doctor has additional information"

## Demo scenarios (both verified working)

PAT-002 — Penicillin anaphylaxis:
  Amoxicillin 500mg prescribed → CRITICAL direct allergy flag
  Cephalexin flagged HIGH cross-reactivity
  Azithromycin cleared as safest
  Doctor confirms

PAT-005 — Polypharmacy QT risk:
  Azithromycin prescribed → QT_PROLONGATION + DRUG_INTERACTION flags
  Doxycycline shown as safer alternative
  Doctor can override with reason code

## Deployment
AWS Elastic Beanstalk — eb deploy from project root (Windows: eb deploy)
Check logs: eb logs
Health check: curl http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/health
Audit dashboard: http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/audit-dashboard

## Known SSE issue
Prompt Opinion's SSE client occasionally drops connections after ~25 seconds
(visible as 200 783 in nginx logs). The tool executes correctly server-side.
Fix: open a fresh session in Prompt Opinion. Works on retry every time.
This is a Prompt Opinion platform behavior, not a server bug.

## Environment variables (AWS EB)
HMAC_SECRET — production HMAC signing key
LOW_STOCK_THRESHOLD — default 10
STOCKOUT_WINDOW_HOURS — default 4
O_GITHUB_TOKEN — GitHub Models API token for classifier

## Local development (Windows)
cd "K:\A Collarbone\ACODE\Formulari-Bridge"
venv\Scripts\activate
$env:HMAC_SECRET="dev-secret"
$env:O_GITHUB_TOKEN="ghp_xxxx"
uvicorn main:app --host 0.0.0.0 --port 8000
