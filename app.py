from enum import Enum
from typing import TypedDict
import os
import re

import streamlit as st
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph

load_dotenv()

# Set up Langsmith
if "langsmith_initialized" not in st.session_state:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
    os.environ["LANGCHAIN_PROJECT"] = "robin-msk-triage"
    st.session_state["langsmith_initialized"] = True

# LLM
llm = ChatAnthropic(model="claude-sonnet-4-6", 
    api_key=st.secrets["ANTHROPIC_API_KEY"])

class TriageOutcome(str, Enum):
    CONTINUE_PROGRAM = "Continue Program"
    REST_AND_MONITOR = "Rest and Monitor"
    ESCALATE_CARE_TEAM = "Escalate Care Team"

class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class State(TypedDict):
    user_input: str
    pain_level: str
    area: str
    outcome: str
    confidence: str
    red_flags: str
    response: str

RED_FLAG_PHRASES = [
    "heard a pop",
    "can\'t bear weight",
    "cannot bear weight",
    "can't bear weight",
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

ROUTING_PROMPT = ChatPromptTemplate.from_template(
    """You are Robin, a conservative rehabilitation triage assistant for a musculoskeletal pain program.

Your role: Safely route members to one of three outcomes based on symptom severity and clinical concern.

OUTCOMES:

1. CONTINUE_PROGRAM
   - Member is experiencing expected, normal training response (DOMS)
   - Pain is mild to moderate (3-5/10), localized, not radiating
   - Full range of motion maintained
   - Pain stable or improving
   - High confidence required

2. REST_AND_MONITOR
   - Pain is elevated above normal soreness, or symptoms are uncertain/ambiguous
   - Pain worsening or unusual quality
   - Post-exercise flare-up or delayed reaction
   - No red flags but warrants caution
   - Conservative default when uncertain

3. ESCALATE_CARE_TEAM
   - Worsening pain despite rest
   - Radiating, neurological, or acute injury symptoms
   - Severe pain (7+/10) or loss of function
   - Member uncertainty about whether symptoms are normal
   - Anything that suggests clinical review is needed

DECISION CRITERIA:
- Conservative bias: When uncertain, choose REST_AND_MONITOR or ESCALATE, never CONTINUE
- Trajectory matters: Worsening over time = clinical concern
- Ambiguity = caution: "Doesn't feel right" from member = take seriously
- Pain level context: Evaluate against baseline and expected response

Member input: {user_input}
Pain level reported: {pain_level}
Area: {area}

Return JSON with keys: outcome, confidence, reasoning
Be explicit about why this outcome was chosen.
"""
)

AREA_PROMPT = ChatPromptTemplate.from_template(
    "Classify the musculoskeletal pain area from the user's input. "
    "Areas: Neck & Upper Back, Shoulders, Elbows, Forearms, Wrists & Hands, Lower Back & Hips, "
    "Pelvic region, Thighs & Knees, Ankles & Feet. If not matching, say 'Other'. "
    "Input: {user_input}"
)

ADVICE_PROMPT = ChatPromptTemplate.from_template(
    """You are a compassionate, knowledgeable physical therapy coach. Provide safe, practical guidance based on the triage outcome.

Area of pain: {area}
Reported pain level: {pain_level}
Triage outcome: {outcome}

GUIDANCE STRUCTURE:

If outcome is ESCALATE_CARE_TEAM:
- Acknowledge the concern without alarming
- Explain why clinical review is needed (be specific)
- DO NOT give exercise guidance
- Provide clear next steps (contact PT, see doctor, urgent care if severe)
- Reassure that escalation is protective

If outcome is REST_AND_MONITOR:
- Acknowledge the elevated pain/symptoms
- Recommend 24-48 hour rest from structured exercise
- Suggest gentle mobility (walking, stretching, light activity)
- Explain what might be causing this response
- Define specific red-flag signs to watch for (worsening, spread, numbness, etc.)
- Clear criteria for returning to full program

If outcome is CONTINUE_PROGRAM:
- Validate the soreness as normal and expected (DOMS)
- Explain why this is a good sign (training adaptation)
- Suggest safe progression strategies (warm-up, gradual intensity)
- Define red flags that would trigger rest or escalation
- Encourage adherence with confidence

Be warm, clear, and action-oriented. Help the member understand their symptoms in context.
"""
)

def detect_red_flags(user_input: str) -> list[str]:
    lower = user_input.lower()
    flags = [phrase for phrase in RED_FLAG_PHRASES if phrase in lower]
    return flags

# Nodes

def classify_area(state: State):
    chain = AREA_PROMPT | llm | StrOutputParser()
    area = chain.invoke({"user_input": state["user_input"]}).strip()
    return {"area": area}


def infer_triage(state: State):
    red_flags = detect_red_flags(state["user_input"])
    if red_flags:
        return {
            "outcome": TriageOutcome.ESCALATE_CARE_TEAM.value,
            "confidence": ConfidenceLevel.HIGH.value,
            "red_flags": ", ".join(red_flags),
        }

    chain = ROUTING_PROMPT | llm | StrOutputParser()
    result = chain.invoke({
        "user_input": state["user_input"],
        "pain_level": state["pain_level"],
        "area": state["area"],
    }).strip()

    outcome_match = re.search(r'"outcome"\s*:\s*"([A-Z_]+)"', result)
    confidence_match = re.search(r'"confidence"\s*:\s*"(HIGH|MEDIUM|LOW)"', result)
    if outcome_match:
        outcome = outcome_match.group(1)
    else:
        outcome = TriageOutcome.REST_AND_MONITOR.name

    return {
        "outcome": outcome,
        "confidence": confidence_match.group(1) if confidence_match else ConfidenceLevel.MEDIUM.value,
        "red_flags": ", ".join(red_flags),
    }


def generate_advice(state: State):
    if state["area"] == "Other":
        return {"response": "Please specify a musculoskeletal area or describe the location more clearly."}

    chain = ADVICE_PROMPT | llm | StrOutputParser()
    response = chain.invoke({
        "area": state["area"],
        "outcome": state["outcome"],
        "pain_level": state["pain_level"],
    })
    return {"response": response}

# Graph
state_type = State
graph = StateGraph(state_type)
graph.add_node("classify", classify_area)
graph.add_node("triage", infer_triage)
graph.add_node("advise", generate_advice)
graph.add_edge("classify", "triage")
graph.add_edge("triage", "advise")
graph.set_entry_point("classify")

app = graph.compile()

# Streamlit UI
st.title("Musculoskeletal Pain AI Agent")

user_input = st.text_area("Describe your pain and activity, including how it started:")
pain_level = st.selectbox("Pain level:", ["mild", "moderate", "severe"])

if st.button("Get Advice"):
    if not user_input.strip():
        st.warning("Please enter your pain description.")
    else:
        initial_state = {
            "user_input": user_input,
            "pain_level": pain_level,
            "area": "",
            "outcome": "",
            "confidence": "",
            "red_flags": "",
            "response": "",
        }
        result = app.invoke(initial_state)
        st.markdown("### Triage Result")
        st.write("**Outcome:**", result["outcome"])
        st.write("**Confidence:**", result["confidence"])
        if result.get("red_flags"):
            st.write("**Red flags detected:**", result["red_flags"])
        st.markdown("### Recommended Guidance")
        st.write(result["response"])
        st.markdown("---")
        st.write("**Remember:** this tool is advisory only and not a substitute for professional medical review.")
