# ruff: noqa
import re
import os
import json
import logging
import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field

from google.adk.agents import Agent, LlmAgent
from google.adk.apps import App
from google.adk.workflow import Workflow, node, FunctionNode, JoinNode, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.tools import McpToolset, AgentTool
from mcp import StdioServerParameters
from google.genai import types

from app.config import config

# Set up logging for audit log
logger = logging.getLogger("career_coach_security")

# Pydantic models for structured output
class ResumeAnalysisOutput(BaseModel):
    skills: List[str] = Field(description="List of key skills identified in the resume.")
    strengths: List[str] = Field(description="Identified professional strengths.")
    gaps: List[str] = Field(description="Skill or experience gaps relative to target roles.")
    summary: str = Field(description="A brief summary of the resume analysis.")

class CareerPlanOutput(BaseModel):
    recommended_courses: List[str] = Field(description="List of recommended online courses to bridge skill gaps.")
    portfolio_projects: List[str] = Field(description="Suggested projects to build to showcase skills.")
    target_roles: List[str] = Field(description="Potential roles suited for the candidate.")

class CoverLetterOutput(BaseModel):
    cover_letter: str = Field(description="The complete drafted cover letter text.")
    tips: List[str] = Field(description="Tips for tailoring this letter further.")

class OrchestratorOutput(BaseModel):
    analysis: ResumeAnalysisOutput = Field(description="Structured resume analysis output.")
    plan: CareerPlanOutput = Field(description="Structured career plan / course / project recommendations.")
    message: str = Field(description="Response message summarizing the findings.")

# MCP toolset configuration
mcp_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command="uv",
        args=["run", "app/mcp_server.py"],
    )
)

# Specialized sub-agents
resume_analyst = LlmAgent(
    name="resume_analyst",
    model=config.model,
    instruction=(
        "You are an expert resume analyst. Analyze the user's resume text to "
        "identify skills, strengths, and experience gaps. First, use the fetch_job_skills tool "
        "to fetch skills needed for their target roles. Then, compare them with the user's resume "
        "and identify gaps. Finally, you MUST call the set_model_response tool to submit your "
        "findings as ResumeAnalysisOutput. Do not output plain text directly."
    ),
    tools=[mcp_toolset],
    output_schema=ResumeAnalysisOutput
)

career_planner = LlmAgent(
    name="career_planner",
    model=config.model,
    instruction=(
        "You are a career planner. Suggest relevant online courses and portfolio "
        "projects to help the user bridge their skill gaps. Use search_courses and get_project_ideas "
        "from the toolset to find actual recommendations. Finally, you MUST call the set_model_response "
        "tool to submit your recommendations as CareerPlanOutput. Do not output plain text directly."
    ),
    tools=[mcp_toolset],
    output_schema=CareerPlanOutput
)

cover_letter_writer = LlmAgent(
    name="cover_letter_writer",
    model=config.model,
    instruction=(
        "You are a cover letter writing specialist. Draft a professional, tailored "
        "cover letter based on the resume analysis and plan."
    ),
    output_schema=CoverLetterOutput
)

# Orchestrator agent using tools to call sub-agents
orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=config.model,
    instruction=(
        "You are the Career Coach Orchestrator. Coordinate the coaching process. "
        "First, use the resume_analyst tool to analyze the user's resume and get skills/strengths/gaps. "
        "Then, use the career_planner tool to get course and project recommendations based on those gaps. "
        "Combine their outputs and you MUST call the set_model_response tool to submit the "
        "final combined OrchestratorOutput response. Rely entirely on the resume_analyst and "
        "career_planner tools. Do not output plain text directly."
    ),
    tools=[
        AgentTool(resume_analyst),
        AgentTool(career_planner)
    ],
    output_schema=OrchestratorOutput
)

# Conversational agent for greetings and general questions (no structured output)
conversational_agent = LlmAgent(
    name="conversational_agent",
    model=config.model,
    instruction=(
        "You are a friendly Career Coach assistant. Help users understand what you can do and "
        "guide them to provide their resume text so you can analyze it. "
        "Answer general career questions helpfully. "
        "Tell users you can analyze their resume, identify skill gaps, recommend courses and projects, "
        "and draft a tailored cover letter when they provide their resume."
    ),
)

# Workflow Function Nodes

@node
def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Checks user input for security threats and scrubs PII."""
    text = ""
    if hasattr(node_input, "parts") and node_input.parts:
        text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, str):
        text = node_input

    # 1. PII Scrubbing
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    sanitized_text = re.sub(email_pattern, "[REDACTED_EMAIL]", text)
    sanitized_text = re.sub(phone_pattern, "[REDACTED_PHONE]", sanitized_text)

    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", 
        "system prompt", 
        "jailbreak", 
        "bypass security",
        "override system"
    ]
    detected_injection = False
    for kw in injection_keywords:
        if kw in text.lower():
            detected_injection = True
            break

    # 3. Domain-specific rule (length check)
    max_length_limit = 10000
    if len(text) > max_length_limit:
        audit_log = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "severity": "WARNING",
            "event": "INPUT_LENGTH_EXCEEDED",
            "details": f"Input length of {len(text)} exceeds limit of {max_length_limit}."
        }
        logger.warning(json.dumps(audit_log))
        sanitized_text = sanitized_text[:max_length_limit]

    # Structured audit log
    if detected_injection:
        audit_log = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "severity": "CRITICAL",
            "event": "PROMPT_INJECTION_DETECTED",
            "details": "Injection keywords found in user input."
        }
        logger.error(json.dumps(audit_log))
        return Event(output="Security Check Failed: Prompt Injection Detected.", route="security_event")

    audit_log = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "severity": "INFO",
        "event": "SECURITY_CHECK_PASSED",
        "details": "Input scrubbed of PII and verified clean."
    }
    logger.info(json.dumps(audit_log))

    sanitized_content = types.Content(role="user", parts=[types.Part.from_text(text=sanitized_text)])
    return Event(output=sanitized_content, route="proceed")

@node
def intake_router(ctx: Context, node_input: types.Content) -> Event:
    """Routes the request based on whether the user provided resume content."""
    text = ""
    if hasattr(node_input, "parts") and node_input.parts:
        text = " ".join(part.text for part in node_input.parts if part.text).lower()

    # Heuristic: treat as resume if message is long enough or contains resume keywords
    resume_keywords = [
        "resume", "cv", "curriculum vitae", "work experience", "skills", "education",
        "job title", "employment", "bachelor", "master", "degree", "university",
        "linkedin", "certif", "internship", "volunteer"
    ]
    has_resume = len(text) > 200 or any(kw in text for kw in resume_keywords)

    if has_resume:
        return Event(output=node_input, route="has_resume")
    else:
        return Event(output=node_input, route="no_resume")


@node(rerun_on_resume=True)
async def run_orchestrator(ctx: Context, node_input: types.Content) -> OrchestratorOutput:
    """Invokes the orchestrator agent and returns its structured result."""
    result = await ctx.run_node(orchestrator_agent, node_input=node_input)
    return result


@node(rerun_on_resume=True)
async def conversational_response(ctx: Context, node_input: types.Content) -> Event:
    """Handles conversational messages (greetings, general questions) without structured output."""
    result = await ctx.run_node(conversational_agent, node_input=node_input)
    # result is plain text from the LlmAgent
    msg = result if isinstance(result, str) else str(result)
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
    yield Event(output=msg)

@node
async def hitl_consent(ctx: Context, node_input: OrchestratorOutput) -> Event:
    """Prompts the user for cover letter consent using RequestInput."""
    # Store orchestrator output in ctx.state for cover letter writer
    ctx.state["orchestrator_result"] = node_input.model_dump()

    if not ctx.resume_inputs or "cover_letter_consent" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="cover_letter_consent",
            message=(
                f"### Resume Analysis Summary\n{node_input.analysis.summary}\n\n"
                f"### Course Recommendations\n" + "\n".join(f"- {c}" for c in node_input.plan.recommended_courses) + "\n\n"
                f"Would you like me to draft a tailored cover letter based on this analysis? "
                f"Please reply 'yes' to proceed, or 'no' to finish."
            )
        )
        return

    consent_response = ctx.resume_inputs["cover_letter_consent"].lower().strip()
    if consent_response in ["yes", "y"]:
        yield Event(output="User agreed to cover letter drafting.", route="draft")
    else:
        yield Event(output="Career planning complete. Cover letter skipped.", route="skip")

@node(rerun_on_resume=True)
async def run_cover_letter_writer(ctx: Context, node_input: str) -> Event:
    """Manually runs the cover letter writer and outputs the content."""
    analysis_data = ctx.state.get("orchestrator_result", {})
    prompt = (
        f"Draft a customized cover letter. Here is the resume analysis and plan:\n"
        f"{json.dumps(analysis_data, indent=2)}\n\n"
        f"Please write a professional cover letter."
    )
    result = await ctx.run_node(cover_letter_writer, node_input=prompt)
    
    # Yield content for the playground UI and output for programmatic use
    msg = f"### Tailored Cover Letter Draft\n\n{result.cover_letter}"
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
    yield Event(output=result.model_dump())

@node
def security_handler(ctx: Context, node_input: str) -> Event:
    """Handles prompt injection or security failures."""
    msg = f"⚠️ **Security Event**: {node_input}"
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
    yield Event(output=msg)

@node
def final_output(ctx: Context, node_input: Any) -> Event:
    """Produces the final output for the workflow."""
    if isinstance(node_input, dict) and "cover_letter" in node_input:
        msg = f"### Draft Complete\nYour cover letter is ready and stored."
        yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
        yield Event(output=node_input)
    elif isinstance(node_input, str):
        yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=node_input)]))
        yield Event(output=node_input)
    else:
        yield Event(output=node_input)

from google.adk.workflow import Edge

# Edge list defining workflow graph topology
edges = [
    Edge(from_node=START, to_node=security_checkpoint),
    Edge(from_node=security_checkpoint, to_node=intake_router, route="proceed"),
    Edge(from_node=security_checkpoint, to_node=security_handler, route="security_event"),
    Edge(from_node=intake_router, to_node=run_orchestrator, route="has_resume"),
    Edge(from_node=intake_router, to_node=conversational_response, route="no_resume"),
    Edge(from_node=run_orchestrator, to_node=hitl_consent),
    Edge(from_node=hitl_consent, to_node=run_cover_letter_writer, route="draft"),
    Edge(from_node=hitl_consent, to_node=final_output, route="skip"),
    Edge(from_node=run_cover_letter_writer, to_node=final_output),
    Edge(from_node=conversational_response, to_node=final_output),
    Edge(from_node=security_handler, to_node=final_output)
]


career_coach_workflow = Workflow(
    name="career_coach_workflow",
    edges=edges,
    description="A secure multi-agent career coaching and planning assistant.",
    rerun_on_resume=True
)

root_agent = career_coach_workflow

app = App(
    root_agent=root_agent,
    name="app",
)
