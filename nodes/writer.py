# nodes/writer.py
import logging
import re
from model import LLMSingleton
from brand_rag import BrandRAG
from learning_memory import FeedbackPortSQL
from brand_metrics import BrandMetricsSQL
from prompts.writer import WRITER_INITIAL, WRITER_REVISION
from graph.state import GraphState

logger = logging.getLogger(__name__)
from utils.observe import observe


DEFAULT_METRICS = {
    "tone": "warm, conversational",
    "perspective": "first-person plural (we/our)",
    "style": "short punchy sentences",
    "avoid": ["passive voice", "corporate jargon"]
}

GENERIC_EXAMPLES = """
Example 1: Community-focused storytelling
"We believe every customer should feel valued. Here's how we do it..."

Example 2: Benefit-led messaging
"Looking for sustainable fashion? Our new collection is here..."
"""

DEFAULT_PATTERNS = {
    "approved": [],
    "rejected": []
}


def _sanitize_research(research: str) -> str:
    """
    Remove all quotable, copyable text from research so the writer
    cannot copy phrases, statistics, names, or buzzwords.
    Converts to conceptual topic markers only.
    """
    if not research:
        return ""

    cleaned = research

    # Remove all quoted text — replace with marker
    cleaned = re.sub(r'"[^"]*"', '[QUOTE]', cleaned)

    # Remove all single-quoted text
    cleaned = re.sub(r"'[^']*'", '[QUOTE]', cleaned)

    # Remove all parenthetical citations and attributions
    cleaned = re.sub(r'\([^)]*\)', '', cleaned)

    # Remove named sources: "per Name on Platform", "Name on Platform", "Name at Company"
    cleaned = re.sub(r'\b\w+\s+(on|at|via|from)\s+\w+\b', '', cleaned, flags=re.IGNORECASE)

    # Remove attribution phrases
    cleaned = re.sub(r'\b(?:as\s+)?(?:noted|discussed|highlighted|stated|seen|mentioned|reported|cited|quoted|according\s+to)\s+(?:by|on|in|from|at)?\s*[^.\n]*', '', cleaned, flags=re.IGNORECASE)

    # Remove all percentages and statistics
    cleaned = re.sub(r'\d+%', '[STAT]', cleaned)
    cleaned = re.sub(r'\d+\s+(?:percent|people|brands|consumers|users|customers|of)', '[STAT]', cleaned, flags=re.IGNORECASE)

    # Remove all numbers that look like years or counts
    cleaned = re.sub(r'\b(?:19|20)\d{2}\b', '[YEAR]', cleaned)
    cleaned = re.sub(r'\b\d{1,3}(?:,\d{3})+\b', '[NUMBER]', cleaned)

    # Remove markdown formatting
    cleaned = re.sub(r'[#*\-]', '', cleaned)

    # Mask capitalized hyphenated phrases — these are often trend terms
    # e.g., "Hyper-Personalization", "AI-Driven", "Community-Driven"
    cleaned = re.sub(r'\b[A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)+\b', '[TERM]', cleaned)

    # Mask multi-word capitalized phrases — e.g., "Community Driven Growth"
    cleaned = re.sub(r'\b(?:[A-Z][a-zA-Z]*\s+){1,4}[A-Z][a-zA-Z]*\b', '[TERM]', cleaned)

    # Clean up empty lines
    lines = [l.strip() for l in cleaned.split('\n') if l.strip()]

    # Remove lines that are too short or just punctuation after cleaning
    lines = [l for l in lines if len(l) > 10 and not l.strip('().,;: ')]

    # If nothing left, return minimal topic marker
    if not lines:
        return "Topic research available. Write from brand experience."

    return '\n'.join(lines)


def _extract_opening(text: str) -> str:
    """Extract the first 3 non-empty lines as the opening pattern."""
    lines = [l for l in text.strip().split('\n') if l.strip()]
    return '\n'.join(lines[:3])


def _extract_closing(text: str) -> str:
    """Extract the last 3 non-empty lines as the closing pattern."""
    lines = [l for l in text.strip().split('\n') if l.strip()]
    return '\n'.join(lines[-3:])


def _extract_section(text: str, header: str) -> str:
    """
    Extract a named section from the brand_brains synthesis text.
    Sections are delimited by lines starting with '#'.
    """
    lines = text.split('\n')
    capture = False
    result = []
    for line in lines:
        if header.upper() in line.upper():
            capture = True
            continue
        if capture and line.strip().startswith('#'):
            break
        if capture:
            result.append(line)
    return '\n'.join(result).strip()


def _build_examples_block(raw_examples: str) -> str:
    """
    Structure RAG examples into opening/closing pattern callouts
    plus the full example for voice reference.
    """
    opening = _extract_opening(raw_examples)
    closing = _extract_closing(raw_examples)
    return f"""OPENING PATTERN — match this energy and structure for your opening:
{opening}

CLOSING PATTERN — match this for your closing:
{closing}

FULL EXAMPLE — study voice only, do not reproduce content:
{raw_examples}"""


def _build_hard_constraint_feedback(hard_constraints: dict) -> str:
    """
    Format hard constraint evidence into actionable rewrite instructions
    for the writer revision prompt.
    """
    if not hard_constraints or not isinstance(hard_constraints, dict):
        return ""

    parts = ["HARD CONSTRAINT FAILURES — fix these exact issues:"]
    for key, value in hard_constraints.items():
        if isinstance(value, dict) and value.get("status") == "fail":
            evidence = value.get("evidence", "")
            required = value.get("required", "")
            rewrite = value.get("rewrite_instruction", "")
            parts.append(f"""
[{key.upper()}]
Your text: "{evidence}"
Required: {required if required else "Follow the brand's structural template for this element."}
Action: Rewrite to match the brand's {key} requirements exactly.""")
        elif isinstance(value, str) and value.lower() == "fail":
            parts.append(f"""
[{key.upper()}]
Status: FAILED
Action: Rewrite to match the brand's {key} requirements exactly.""")

    return "\n".join(parts) if len(parts) > 1 else ""


@observe("writer_node")
def writer_node(state: GraphState, rag: BrandRAG, analyzer: BrandMetricsSQL,
                memory: FeedbackPortSQL) -> GraphState:
    """
    Generates or revises brand-consistent content.
    """
    topic        = state["topic"]
    content_type = state["content_type"]
    research     = state["research"]
    feedback     = state.get("feedback", "")
    iteration    = state.get("iteration", 0) + 1

    # Sanitize research to prevent copying
    sanitized_research = _sanitize_research(research)

    try:
        metrics = analyzer.get_context()
    except Exception as e:
        logger.warning("Metrics analyzer failed, using defaults: %s", e)
        metrics = str(DEFAULT_METRICS)

    # Extract high-signal sections from brand brain for focused injection
    generation_instructions = _extract_section(metrics, "GENERATION INSTRUCTIONS")
    signature_phrases       = _extract_section(metrics, "SIGNATURE PHRASES")
    opening_formula         = _extract_section(metrics, "OPENING FORMULA")
    closing_formula         = _extract_section(metrics, "CLOSING FORMULA")

    # NEW: Extract intellectual patterns from brand brain
    diagnostic_style       = _extract_section(metrics, "DIAGNOSTIC STYLE")
    value_hierarchy        = _extract_section(metrics, "VALUE HIERARCHY")
    reframing_moves        = _extract_section(metrics, "REFRAMING MOVES")
    authority_source       = _extract_section(metrics, "AUTHORITY SOURCE")
    argument_structure     = _extract_section(metrics, "ARGUMENT STRUCTURE")
    thinking_templates     = _extract_section(metrics, "THINKING TEMPLATES")

    # Fall back gracefully if sections are missing (cold start / sparse brain)
    if not generation_instructions:
        generation_instructions = (
            "Write in first-person plural (we/our). Be direct and authoritative. "
            "Open with a provocative truth. Close with a one-line CTA. "
            "Ground every claim in a specific number, timeframe, or client outcome."
        )
    if not signature_phrases:
        signature_phrases = "None extracted yet — rely on brand voice metrics above."
    if not opening_formula:
        opening_formula = (
            "Open with a direct provocative truth or uncomfortable fact that names a common mistake. "
            "Never open with a rhetorical question. Never open with a scene-setter."
        )
    if not closing_formula:
        closing_formula = (
            "Close with a short punchy one-liner or direct CTA. "
            "Example pattern: 'Ready to X? Let's Y.' or 'Because X every time.'"
        )

    # NEW: Fall back for intellectual patterns
    if not diagnostic_style:
        diagnostic_style = "Diagnose problems as failures of intention or clarity, not failures of knowledge or effort."
    if not value_hierarchy:
        value_hierarchy = "Prioritize consistency over creativity, authenticity over performance, relationship over transaction."
    if not reframing_moves:
        reframing_moves = "Redefine common concepts by negation and contrast. 'Not X. Y.'"
    if not authority_source:
        authority_source = "Ground claims in brand's own experience with specific numbers and client outcomes."
    if not argument_structure:
        argument_structure = "Observation → pattern → diagnosis → prescription → outcome."
    if not thinking_templates:
        thinking_templates = "- 'The brands that win are the ones that...'\n- 'We've seen brands [failure] — and then [outcome]. Why? Because [diagnosis].'"

    try:
        raw_examples = rag.query(topic)
        examples = _build_examples_block(raw_examples)
    except Exception as e:
        logger.warning("RAG failed, using generic examples: %s", e)
        examples = GENERIC_EXAMPLES

    try:
        patterns = memory.get_patterns(content_type)
    except Exception as e:
        logger.warning("Memory failed, using empty patterns: %s", e)
        patterns = DEFAULT_PATTERNS

    approved = [p["angle"] for p in patterns.get("approved", [])][:3]
    rejected = [p["angle"] for p in patterns.get("rejected", [])][:2]

    if iteration == 1:
        prompt = WRITER_INITIAL.format(
            topic=topic,
            content_type=content_type,
            research=sanitized_research,
            metrics=metrics,
            generation_instructions=generation_instructions,
            signature_phrases=signature_phrases,
            opening_formula=opening_formula,
            closing_formula=closing_formula,
            # NEW: Intellectual patterns
            diagnostic_style=diagnostic_style,
            value_hierarchy=value_hierarchy,
            reframing_moves=reframing_moves,
            authority_source=authority_source,
            argument_structure=argument_structure,
            thinking_templates=thinking_templates,
            examples=examples,
            approved="\n".join(approved) if approved else "None yet",
            rejected="\n".join(rejected) if rejected else "None yet"
        )
    else:
        # Build hard constraint feedback from enforcer evidence
        hard_constraints = state.get("hard_constraint_evidence", {})
        hard_constraint_feedback = _build_hard_constraint_feedback(hard_constraints)

        prompt = WRITER_REVISION.format(
            previous_content=state.get("content", ""),
            feedback=feedback,
            hard_constraint_feedback=hard_constraint_feedback,
            style_match=state.get("style_match", 0.0),
            tone_match=state.get("tone_match", 0.0),
            structure_match=state.get("structure_match", 0.0),
            signature_match=state.get("signature_match", 0.0),
            metrics=metrics,
            generation_instructions=generation_instructions,
            signature_phrases=signature_phrases,
            opening_formula=opening_formula,
            closing_formula=closing_formula,
            # NEW: Intellectual patterns
            diagnostic_style=diagnostic_style,
            value_hierarchy=value_hierarchy,
            reframing_moves=reframing_moves,
            authority_source=authority_source,
            argument_structure=argument_structure,
            thinking_templates=thinking_templates,
            examples=examples
        )

    try:
        result = LLMSingleton.get().invoke(prompt)
        content = result.content
    except Exception as e:
        logger.error("LLM failed: %s", e)
        content = f"[System Error: Unable to generate content - {str(e)[:80]}]"

    logger.info("Writer iteration=%d complete for topic=%r", iteration, topic)

    return {
        **state,
        "content": content,
        "iteration": iteration
    }