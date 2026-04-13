# Formulari Bridge — Claude Code Context

## What this project is
A FastAPI MCP server for outpatient pharmacy drug substitution,
built for the Agents Assemble Healthcare AI Hackathon (Prompt Opinion / Darena Health).

All patient data is SYNTHETIC. No real PHI anywhere in this repo.

## Architecture
Three-agent A2A system on Prompt Opinion platform:
- Agent A (Clinical Copilot): doctor-facing interface
- Agent B (Hardware Sentinel): calls MCP tools for inventory/logistics
- Agent C (Safety Auditor): receives SHARP FHIR context + rules engine flags, explains to doctor

MCP Server (this repo): FastAPI, 5 tools, HMAC audit trail, rules engine.

## File structure
- main.py          — FastAPI app, all 5 MCP tools, rules engine, audit trail
- mock_db.json     — 25 synthetic drugs, 5 synthetic FHIR patient bundles
- requirements.txt — Python dependencies
- .env.example     — environment variable template (copy to .env, fill in)

## Critical rules — DO NOT change these without explicit instruction
1. The rules engine in main.py fires contraindication flags. The LLM explains them.
   Never modify the rules engine to delegate flag generation to an LLM.
2. HMAC_SECRET must come from environment variable — never hardcode.
3. All patient data stays synthetic. Never add real patient data.
4. No auto-approval logic anywhere — every substitution requires doctor confirmation.
5. mock_db.json is the single source of truth for drug and patient data.

## Running locally
```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with a real HMAC_SECRET
uvicorn main:app --reload --port 8000
```

Then visit:
- http://localhost:8000/docs       — Swagger UI for all tools
- http://localhost:8000/health     — health check
- http://localhost:8000/demo/full-scenario — end-to-end demo

## MCP tools (endpoints)
- POST /tools/getHardwareInventory
- POST /tools/getLogisticsEstimate
- POST /tools/getFormularyAlternatives   ← main clinical reasoning tool
- POST /tools/flagLowStockReplenishment
- POST /tools/getAuditTrace

## When Claude Code is asked to add a feature
- Add it to main.py unless it is new drug/patient data (mock_db.json)
- Keep all tool endpoints under /tools/ prefix
- Any new tool must: log to audit trail, accept job_id and sharp_context_hash
- Test with /demo/full-scenario before considering done

## Deployment target
AWS Elastic Beanstalk (same pattern as IaC Sentinel project).
Docker container, ECR registry.
