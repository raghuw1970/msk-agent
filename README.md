# Musculoskeletal Pain AI Agent

A proof-of-concept agentic AI triage system for musculoskeletal pain rehabilitation, built to explore **clinical safety in conversational care assistance**.

## What This Demonstrates

This prototype explores three core product design challenges:

1. **Consequence-weighted autonomy** — Where should the human-in-the-loop line be drawn based on symptom severity?
2. **Layered safety architecture** — Why safety-critical decisions should be deterministic (rule-based), not probabilistic (LLM-based)
3. **Evaluation framework design** — How to measure whether a clinical AI makes the right decisions when ground truth is ambiguous

## Architecture

The system uses a **three-layer triage flow**:

```
Member Input
    ↓
[RED FLAG DETECTOR] — Deterministic rule-based layer
    ↓ No red flags
[LLM TRIAGE ROUTER] — Claude-based conversational routing
    ↓
[OUTCOME ROUTER] 
├─ CONTINUE_PROGRAM
├─ REST_AND_MONITOR  
└─ ESCALATE_CARE_TEAM
```

### Three Triage Outcomes

**CONTINUE_PROGRAM** — Normal soreness, safe to continue
- Member is experiencing expected training response (DOMS)
- Mild to moderate pain, localized, full range of motion
- High confidence required

**REST_AND_MONITOR** — Caution warranted, 24–48hr rest
- Pain elevated above normal soreness
- Ambiguous or uncertain symptoms
- Conservative default when uncertain

**ESCALATE_CARE_TEAM** — Human clinical review required
- Worsening pain despite rest
- Red flags detected (heard a pop, can't bear weight, numbness, etc.)
- Severe pain or loss of function

## Documentation

- [TRIAGE_NARRATIVE.md](TRIAGE_NARRATIVE.md) — Complete system narrative, decision logic, and safety guardrails
- [eval_scenarios.py](eval_scenarios.py) — Five core evaluation scenarios (EVAL_001 through EVAL_005)
- [eval_runner.py](eval_runner.py) — Evaluation runner to validate system performance

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Anthropic API key and LangSmith credentials
   ```

3. **Run the Streamlit app:**
   ```bash
   streamlit run app.py
   ```
   The app will be available at `http://localhost:8501`

## Usage

### Interactive Web App

1. Describe your pain and where it's located
2. Select your pain level (mild, moderate, severe)
3. Get triage outcome and personalized guidance

The app shows:
- **Triage outcome** — Continue Program, Rest and Monitor, or Escalate Care Team
- **Confidence level** — How confident the system is in this decision
- **Red flags detected** — Any safety signals that triggered escalation
- **Guided response** — Outcome-specific advice from the AI coach

### System Evaluation

Validate the system against the five core evaluation scenarios:

```bash
python eval_runner.py
```

This runs EVAL_001 through EVAL_005 and reports pass/fail for:
- Routing correctness
- Safety adherence (safety-critical scenarios)
- Red flag detection accuracy
- Confidence thresholds
- Conservative bias under uncertainty

**Test coverage:**
- EVAL_001: Normal DOMS → CONTINUE_PROGRAM
- EVAL_002: Worsening pain → ESCALATE_CARE_TEAM (safety-critical)
- EVAL_003: Post-exercise flare → REST_AND_MONITOR
- EVAL_004: Acute red flag → ESCALATE_CARE_TEAM (deterministic, safety-critical)
- EVAL_005: Ambiguous symptoms → REST_AND_MONITOR (conservative default)

## Environment Variables

- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `LANGCHAIN_API_KEY`: Your LangSmith API key
- `LANGCHAIN_PROJECT`: Project name for LangSmith (optional)