"""
Evaluation runner for MSK Pain Triage System.

Runs a set of evaluation scenarios against the triage system and generates a report
showing pass/fail status for each scenario and overall system health.

Usage:
    python eval_runner.py
"""

import json
import re
from typing import Dict, List, Tuple

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv

from eval_scenarios import (
    EVAL_SCENARIOS,
    EvalScenario,
    TriageOutcome,
    ConfidenceLevel,
    score_scenario,
    format_scenario_report
)

load_dotenv()

# Initialize LLM
llm = ChatAnthropic(
    model="claude-3-sonnet-20240229",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

# Red flag phrases (same as in app.py)
RED_FLAG_PHRASES = [
    "heard a pop",
    "can't bear weight",
    "cannot bear weight",
    "sharp pain",
    "can't move",
    "cannot move",
    "numbness",
    "tingling",
    "loss of feeling",
    "lost feeling",
    "radiating into",
    "severe pain",
    "unable to",
    "collapse",
    "instability",
]

def detect_red_flags(text: str) -> List[str]:
    """Detect red flag phrases in text."""
    lower = text.lower()
    flags = [phrase for phrase in RED_FLAG_PHRASES if phrase in lower]
    return flags

def infer_area(user_input: str) -> str:
    """Infer pain area using LLM."""
    prompt = ChatPromptTemplate.from_template(
        "Classify the musculoskeletal pain area from this input. "
        "Areas: Neck & Upper Back, Shoulders, Elbows, Forearms, Wrists & Hands, Lower Back & Hips, "
        "Pelvic region, Thighs & Knees, Ankles & Feet. If not matching, say 'Other'. "
        "Input: {user_input}\n\nRespond with only the area name."
    )
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"user_input": user_input}).strip()

def infer_triage(user_input: str, pain_level: str = "moderate", area: str = "") -> Tuple[str, str, List[str]]:
    """
    Infer triage outcome using the red flag detector and LLM router.
    Returns: (outcome, confidence, red_flags_list)
    """
    # Check for red flags first
    red_flags = detect_red_flags(user_input)
    if red_flags:
        return TriageOutcome.ESCALATE_CARE_TEAM.value, ConfidenceLevel.HIGH.value, red_flags

    # If no red flags, use LLM to route
    prompt = ChatPromptTemplate.from_template(
        """You are a conservative rehabilitation triage assistant.

Given the member input, choose one of:
- CONTINUE_PROGRAM (normal soreness, expected response)
- REST_AND_MONITOR (elevated symptoms, uncertain, need caution)
- ESCALATE_CARE_TEAM (worsening, radiating, or clinical concern)

Member input: {user_input}
Pain level: {pain_level}
Area: {area}

Return JSON with keys: outcome, confidence

Examples:
{{"outcome": "CONTINUE_PROGRAM", "confidence": "HIGH"}}
{{"outcome": "REST_AND_MONITOR", "confidence": "MEDIUM"}}
{{"outcome": "ESCALATE_CARE_TEAM", "confidence": "HIGH"}}"""
    )
    chain = prompt | llm | StrOutputParser()
    result = chain.invoke({
        "user_input": user_input,
        "pain_level": pain_level,
        "area": area
    }).strip()

    # Parse JSON response
    try:
        outcome_match = re.search(r'"outcome"\s*:\s*"([A-Z_]+)"', result)
        confidence_match = re.search(r'"confidence"\s*:\s*"(HIGH|MEDIUM|LOW)"', result)
        outcome = outcome_match.group(1) if outcome_match else "REST_AND_MONITOR"
        confidence = confidence_match.group(1) if confidence_match else "MEDIUM"
    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        print(f"Raw response: {result}")
        outcome = "REST_AND_MONITOR"
        confidence = "MEDIUM"

    return outcome, confidence, []

def run_scenario(scenario: EvalScenario) -> Dict:
    """Run a single evaluation scenario and return results."""
    # Use first member message as primary input
    user_input = " ".join(scenario.member_messages)
    
    # Infer area
    area = infer_area(user_input)
    
    # Infer triage
    outcome, confidence, red_flags = infer_triage(user_input, pain_level="moderate", area=area)
    
    # Score the scenario
    outcome_enum = TriageOutcome(outcome)
    scores = score_scenario(scenario, outcome_enum, confidence, red_flags, "")
    
    return {
        "scenario": scenario,
        "actual_outcome": outcome,
        "actual_confidence": confidence,
        "red_flags_detected": red_flags,
        "scores": scores
    }

def run_all_scenarios() -> List[Dict]:
    """Run all evaluation scenarios."""
    print("=" * 80)
    print("MSK PAIN TRIAGE SYSTEM — EVALUATION RUNNER")
    print("=" * 80)
    print()
    
    results = []
    for scenario in EVAL_SCENARIOS:
        print(f"Running: {scenario.id} — {scenario.name}...")
        result = run_scenario(scenario)
        results.append(result)
        print(f"  Outcome: {result['actual_outcome']} (Confidence: {result['actual_confidence']})")
        print(f"  Red flags: {result['red_flags_detected'] or 'None'}")
        print(f"  Status: {'✅ PASS' if result['scores']['overall_pass'] else '❌ FAIL'}")
        print()
    
    return results

def print_report(results: List[Dict]):
    """Print a comprehensive evaluation report."""
    print("=" * 80)
    print("EVALUATION REPORT")
    print("=" * 80)
    print()
    
    passed = sum(1 for r in results if r["scores"]["overall_pass"])
    total = len(results)
    safety_critical_passed = sum(
        1 for r in results 
        if r["scenario"].safety_critical and r["scores"]["overall_pass"]
    )
    safety_critical_total = sum(1 for r in results if r["scenario"].safety_critical)
    
    print(f"Overall: {passed}/{total} scenarios passed ({100*passed//total}%)")
    print(f"Safety-critical: {safety_critical_passed}/{safety_critical_total} passed")
    print()
    
    # Detailed results
    for result in results:
        scenario = result["scenario"]
        scores = result["scores"]
        status = "✅ PASS" if scores["overall_pass"] else "❌ FAIL"
        safety_note = " [SAFETY CRITICAL]" if scenario.safety_critical else ""
        
        print(f"{status} {scenario.id}: {scenario.name}{safety_note}")
        print(f"   Expected: {scenario.expected_outcome.value}")
        print(f"   Actual:   {result['actual_outcome']}")
        print(f"   Scores: ", end="")
        score_items = [
            f"routing={scores['routing_correct']}",
            f"safety={scores['safety_pass']}",
            f"redflags={scores['red_flag_detected']}",
            f"confidence={scores['confidence_adequate']}",
            f"conservative={scores['conservative_bias']}"
        ]
        print(", ".join(score_items))
        print()
    
    # Summary
    print("=" * 80)
    if passed == total:
        print("✅ ALL TESTS PASSED")
    elif safety_critical_passed < safety_critical_total:
        print("❌ SAFETY-CRITICAL FAILURE — SYSTEM NOT READY FOR PRODUCTION")
    else:
        print(f"⚠️  {total - passed} non-critical test(s) failed")
    print("=" * 80)

if __name__ == "__main__":
    results = run_all_scenarios()
    print_report(results)
