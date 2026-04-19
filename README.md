# Formulari Bridge 🏥

> **Clinical intent to pharmacy reality — an AI-powered prescription safety system that eliminates the pharmacist-doctor phone tag loop.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by Claude](https://img.shields.io/badge/Powered%20by-Claude%20Sonnet-blueviolet?logo=anthropic)](https://www.anthropic.com/)
[![FHIR R4](https://img.shields.io/badge/FHIR-R4%20Compliant-blue)](https://hl7.org/fhir/R4/)
[![HIPAA](https://img.shields.io/badge/SHARP-HIPAA%20Audit%20Ready-green)](https://www.hhs.gov/hipaa/)
[![Open Source](https://img.shields.io/badge/Open%20Source-github.com%2Fnurusyda-black?logo=github)](https://github.com/nurusyda/Formulari-Bridge)

<p align="center">
  <a href="https://github.com/nurusyda/Formulari-Bridge">
    <img src="https://img.shields.io/badge/View%20on%20GitHub%20%F0%9F%8F%A5-teal?style=for-the-badge&logo=github&logoColor=white" alt="GitHub">
  </a>
</p>

Every day, a pharmacist discovers a prescribed drug is out of stock. They call the doctor. The doctor is with another patient. The patient waits. Hours pass. Sometimes nothing gets resolved at all.

**Formulari Bridge** intercepts this at the point of prescription — before the patient ever reaches the pharmacy counter. The doctor sees real-time stock, ranked safe alternatives, and safety flags in the same workflow where they write the prescription. One confirmation. Three seconds. Done.

---

## 🧭 Why This Exists

Drug-related harm costs **$528 billion annually** in the US alone (ASHP, 2022). A significant share of this is preventable — wrong drug, wrong dose, stock mismatch, allergy oversight — problems that compound when pharmacists and doctors communicate by phone tag across siloed systems.

I built this because the back-and-forth is not a people problem. It's an architecture problem. The pharmacist knows the stock. The doctor knows the patient. Neither has the other's information at the moment decisions are made.

Formulari Bridge puts both in the same loop — at the right time, with the right safety checks hardcoded in.

---

## ✨ What It Does

- **Real-time stock check** — prescription is validated against live pharmacy inventory the moment it's written
- **Safe alternative ranking** — out-of-stock drugs surface ranked alternatives with wait times and stock status
- **Hardcoded safety rules** — 9 clinical contraindication rules fire before the LLM sees anything
- **Override gates** — doctors can override flags, but must select a reason; every override is logged
- **HMAC audit trail** — cryptographically signed log of every decision, every override, every reason
- **Analytics dashboard** — override patterns, flag distribution, tool call volume for Chief Pharmacist review
- **Patient wait time** — estimated pickup time communicated before patient leaves the consultation room

---

## 🔬 Live Demo Walkthrough

**Patient:** Maria Santos (DOB: 1978-11-22) — documented severe penicillin allergy, reaction: anaphylaxis.

**Prescribed:** Amoxicillin 500mg — a penicillin. Also out of stock.

Two flags fire simultaneously:

```
⛔ OUT OF STOCK
⚠ DIRECT_ALLERGY: Patient has documented Severe allergy to Penicillin. Reaction: Anaphylaxis.
```

System presents ranked options:

```
Option 1: Azithromycin 250mg Tablet     — IN STOCK — 12 min — No flags       ✅ RECOMMENDED
Option 2: Cephalexin 500mg Capsule      — IN STOCK — 15 min — HIGH CROSS_REACTIVITY flag
Option 3: Amoxicillin 250mg Capsule     — IN STOCK — 10 min — Prescriber confirmation required
Option 5: External pharmacies           — MedPlus (4 min walk), Guardian (9 min), Unity (13 min)
```

Doctor overrides to Cephalexin (Option 2). System does not silently allow it:

```
⚠ OVERRIDE CONFIRMATION REQUIRED
You selected Cephalexin 500mg despite active safety flag(s):
  ⚠ DIRECT_ALLERGY — Severe penicillin allergy on record
  ⚠ HIGH CROSS_REACTIVITY — Cephalosporins share ~1-2% cross-reactivity with penicillin

Select reason:
[A] Clinical judgment — benefit outweighs risk
[B] Patient cleared by specialist
[C] Flag not applicable — context has changed
[D] System suggestion incorrect
```

Doctor selects A. Result:

```
✅ DISPENSING CONFIRMED
Override logged. Reason: Clinical judgment: benefit outweighs risk
Audit trail updated. Pharmacist notified.
```

Two contraindication flags on one patient. Both caught. Override gated. Decision traceable.

---

## 🏗️ Architecture

```
[Doctor's Workstation]
        |
        | Prescription Input (natural language or structured)
        ↓
[Classifier Agent — Agent A]
        |
        └── Interprets clinical intent
            "ear infection, 3 days, no allergies" → drug class + dosage parameters
        |
        ↓
[Formulary Lookup Agent — Agent B]
        |
        ├── getHardwareInventory       → live stock levels
        ├── getFormularyAlternatives   → ranked substitutes
        ├── getDoseVariants            → same drug, different strengths
        ├── getExternalPharmacyOptions → nearby alternatives with walk times
        └── getLogisticsEstimate       → wait time per option
        |
        ↓
[Safety & Confirmation Agent — Agent C]
        |
        ├── run_contraindication_rules()   ← HARDCODED — not LLM
        │     Rule 1: Direct allergy match
        │     Rule 2: Penicillin → Cephalosporin cross-reactivity
        │     Rule 3: Macrolide + warfarin interaction
        │     Rule 4: QT prolongation risk
        │     Rule 5: Renal dose adjustment (CrCl < 50)
        │     Rule 6: Metformin CrCl safety check
        │     Rule 7: Therapeutic duplication
        │     Rule 8: NSAID in renal impairment
        │     Rule 9: BX-coded substitution confirmation
        │
        ├── flagLowStockReplenishment  → alerts pharmacy ops
        ├── getPharmacySummary         → patient-facing wait time
        └── confirmDispensing          → final gate with override logging
        |
        ↓
[HMAC Audit Logger]
        |
        └── Every decision cryptographically signed → Audit dashboard
```

### The Safety Model

Safety flags come exclusively from the hardcoded rules engine. **The LLM explains them — it never invents them.** This distinction matters for clinical accountability.

```python
# ——— RULES ENGINE ———————————————————————————————
# This is the safety-critical layer. Flags come from here.
# The LLM (Agent C) explains these flags — it never invents them.

# Rule 1: Direct allergy match
# Rule 2: Penicillin → Cephalosporin cross-reactivity
# Rule 3: Macrolide + warfarin interaction
# Rule 4: QT prolongation risk
# Rule 5: Renal dose adjustment
# Rule 6: Metformin CrCl safety check
# Rule 7: Therapeutic duplication
# Rule 8: NSAID in renal impairment
# Rule 9: BX-coded substitution
```

Every override requires a reason. Every reason is logged. Every log is HMAC-signed.

---

## 📊 Analytics Dashboard

The operational intelligence dashboard surfaces patterns that matter to hospital pharmacists and administrators:

| Metric | What It Shows |
|---|---|
| Override Rate by Flag Type | Which safety flags doctors override most — and why |
| Override Reason Distribution | Clinical judgment vs. specialist clearance vs. system error |
| Most Overridden Drugs | Drugs frequently dispensed despite flags — possible formulary gap |
| Tool Call Volume | Which system tools fire most — operational load visibility |
| Activity by Hour (UTC) | Peak prescription windows for staffing decisions |

Every override is a data point. Aggregate patterns reveal formulary gaps, clinical workflow friction, and safety blind spots that individual incident reviews miss.

---

## 🛡️ Security & Compliance

| Layer | Implementation |
|---|---|
| **HMAC Audit Trail** | Cryptographically signed logs for every prescription decision |
| **Override Logging** | Every override requires a reason; logged with job ID and timestamp |
| **FHIR R4 Compliant** | Full interoperability with modern healthcare data standards |
| **SHARP Extension** | Security, HIPAA, Audit, Risk, and Privacy framework built-in |
| **On-Premise Option** | Clinical LLM per hospital region — patient data never leaves the building |
| **Encrypted Channels** | Internal system communication over encrypted channels only |
| **Least-Privilege Design** | Each agent scoped to minimum required tool access |

### Privacy-First Architecture

```
LAYER 5 — Private    Patient data never leaves the building
LAYER 4 — Secure     Encrypted channels between internal systems
LAYER 3 — Clinical   Clinical workflows processed on-premise
LAYER 2 — Regional   LLM deployment per hospital network
LAYER 1 — Hospital   Data stays within hospital building perimeter
```

---

## 🧰 Tech Stack

```
Agent Framework    : 3 coordinated AI agents (Classifier, Lookup, Safety)
Protocol           : MCP (Model Context Protocol) — 8 clinical tools
LLM                : Claude Sonnet (Anthropic)
Safety Engine      : Hardcoded Python rules — no LLM involvement
Audit              : HMAC-signed cryptographic log chain
Standards          : FHIR R4, SHARP extension
Analytics          : Operational intelligence dashboard
Deployment         : On-premise per hospital region
```

---

## ⚙️ MCP Tools

| Tool | Function |
|---|---|
| `getHardwareInventory` | Live stock levels per drug |
| `getLogisticsEstimate` | Estimated wait time per option |
| `getFormularyAlternatives` | Ranked safe substitutes |
| `getDoseVariants` | Same drug, different strengths/forms |
| `getExternalPharmacyOptions` | Nearby pharmacies with walk times |
| `flagLowStockReplenishment` | Alert pharmacy operations |
| `getPharmacySummary` | Patient-facing pickup summary |
| `confirmDispensing` | Final dispensing gate with override logging |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Anthropic API key (Claude Sonnet)
- MCP server running with hospital formulary data

### Setup

```bash
# Clone repository
git clone https://github.com/nurusyda/Formulari-Bridge.git
cd Formulari-Bridge

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and MCP server config

# Run
python main.py
```

### Environment Variables

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key | ✅ |
| `MCP_SERVER_URL` | MCP server endpoint for formulary tools | ✅ |
| `HMAC_SECRET` | Secret for signing audit log entries | ✅ |
| `HOSPITAL_REGION` | Hospital region identifier | ✅ |
| `ON_PREMISE_MODE` | Set to `true` for local LLM deployment | ❌ |
| `AUDIT_LOG_PATH` | Path for HMAC audit log output | ❌ |

---

## 📁 Project Structure

```
Formulari-Bridge/
├── main.py              # Agent orchestration + MCP tool integration
├── rules_engine.py      # Hardcoded contraindication rules (9 rules)
├── audit.py             # HMAC signing and audit trail
├── dashboard.py         # Analytics dashboard backend
├── prompts.py           # Agent system prompts
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── README.md
```

---

## 📊 Comparison

| Feature | Formulari Bridge | Epic/Cerner | Manual Phone Tag |
|---|---|---|---|
| Real-time stock at prescription | ✅ | ❌ | ❌ |
| Ranked safe alternatives | ✅ | Partial | ❌ |
| Hardcoded safety rules | ✅ (9 rules) | ✅ | Human-dependent |
| Override gate with reason logging | ✅ | Partial | ❌ |
| HMAC audit trail | ✅ | ❌ | ❌ |
| Patient wait time communicated | ✅ | ❌ | ❌ |
| Analytics dashboard | ✅ | ✅ | ❌ |
| Open source | ✅ | ❌ | — |
| Resolution time | ~3 seconds | Hours | Hours |

---

## 🗺️ What's Next

Clinical process automation roadmap:

```
Privacy First  →  On-premise clinical LLM per hospital region
                  Patient data never leaves the building

01 Doctor Writes    →  "ear infection, 3 days, no allergies"
02 Classifier Agent →  Reads and interprets clinical intent
03 Finds Antibiotics →  Automatically searches available matches
04 Doctor Confirms  →  Final approval before prescription issued
```

Near-term:
- EHR integration (Epic, Cerner FHIR R4 endpoints)
- Mobile pharmacist interface
- Predictive stock replenishment from prescription patterns
- Multi-hospital formulary federation

---

## 📚 References

1. Watanabe JH, McInnis T, Hirsch JD. (2018). [Cost of Prescription Drug-Related Morbidity and Mortality](https://pubmed.ncbi.nlm.nih.gov/29577766/). *Annals of Pharmacotherapy*. DOI: 10.1177/1060028018765159. PMID: 29577766
2. ONC. (2023). [FHIR R4 Interoperability Standards](https://www.healthit.gov/topic/standards-technology/standards/fhir-fact-sheets)
3. HHS. (2023). [HIPAA Security Rule — Administrative Safeguards](https://www.hhs.gov/hipaa/for-professionals/security/index.html)
4. HL7. (2023). [FHIR R4 Specification](https://hl7.org/fhir/R4/)

---

## 🤝 Contributing

Pull requests and issues welcome. For significant changes, open an issue first.

Useful contributions:
- Additional contraindication rules (with citations)
- EHR system integrations
- Regional formulary data connectors
- Accessibility improvements for clinical interfaces
- Performance benchmarks on real formulary datasets

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built to close the loop between clinical intent and pharmacy reality.**

*"The pharmacist knew the stock. The doctor knew the patient. Neither had the other's information at the right time. Now they do."*

github.com/nurusyda/Formulari-Bridge

</div>
