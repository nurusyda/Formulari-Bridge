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
  Calls runFullPharmacyCheck_mcp directly.
  Linked agents: Clinical Classifier, Hardware Sentinel, Clinical Synthesiser.
  Never makes clinical decisions. Doctor always confirms.

Agent B — Hardware Sentinel (BYO)
  Inventory and data layer. Called by Agent A when needed.
  Tool: runFullPharmacyCheck_mcp and all individual MCP tools.

Agent C — Clinical Synthesiser (BYO)
  Safety reasoning layer. Ranks alternatives, explains flags in plain English.
  Never invents flags. Only explains what the rules engine returns.
  No MCP tools — reasoning only.

MCP Server (this repo): FastAPI, 9 tools, HMAC audit trail, rules engine.
Deployed: AWS Elastic Beanstalk
URL: http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com

## File structure
- main.py              — FastAPI app, all 9 MCP tools, rules engine, audit trail
- mock_db.json         — synthetic drugs, 5 synthetic FHIR patient bundles
- classifier/
  - classify_intent.py     — GPT-4o classification via GitHub Models API
  - generate_training_data.py — generates training_data.json
  - training_data.json       — 25 few-shot examples for classifier
- prompts.py           — all four agent system prompts
- requirements.txt     — Python dependencies
- .env.example         — environment variable template

## Critical rules — DO NOT change without explicit instruction
1. Rules engine in main.py fires contraindication flags. LLM explains them.
   Never modify rules engine to delegate flag generation to an LLM.
2. HMAC_SECRET must come from environment variable — never hardcode.
3. All patient data stays synthetic. Never add real patient data.
4. No auto-approval logic anywhere — doctor always confirms every substitution.
5. mock_db.json is the single source of truth for drug and patient data.
6. classifyClinicalIntent_mcp must never be called directly by Agent A.
   It is only called when Agent A explicitly consults Clinical Classifier.

## MCP tools (all 9)
- runFullPharmacyCheck_mcp      ← PRIMARY tool, call this first
- getHardwareInventory_mcp
- getLogisticsEstimate_mcp
- getFormularyAlternatives_mcp  ← contains contraindication flags
- getDoseVariants_mcp
- flagLowStockReplenishment_mcp ← recommendation only, never automatic
- getExternalPharmacyOptions_mcp
- getAuditTrace_mcp
- classifyClinicalIntent_mcp    ← ONLY via Agent 0 consult, never directly

## Current known issue being fixed
Agent A occasionally calls classifyClinicalIntent_mcp instead of 
runFullPharmacyCheck_mcp when receiving drug name inputs like 
"Amoxicillin + PAT-002". Fix: update tool descriptions in main.py
to make runFullPharmacyCheck_mcp the unambiguous primary tool and
add explicit DO NOT CALL DIRECTLY warning to classifyClinicalIntent_mcp.

## When Claude Code is asked to add a feature
- Add to main.py unless it is new drug/patient data (mock_db.json)
- Keep all tool endpoints under /tools/ prefix
- Any new tool must: log to audit trail, accept job_id and sharp_context_hash
- Test with /demo/full-scenario before considering done
- After any main.py change: verify syntax, then eb deploy

## Deployment
AWS Elastic Beanstalk — eb deploy from project root
Check logs: eb logs
Health check: curl http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/health