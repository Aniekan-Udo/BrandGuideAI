# nodes/writer.py
import logging
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


def _extract_section(text: str, header: str) -> str:
    """
    Extract a named section from the brand_brains synthesis text.
    Sections are delimited by lines starting with '#'.
    
    Matches by checking if the line (stripped of '#' and whitespace)
    starts with the header — avoids partial matches like 'OPENING'
    matching 'OPENING MOVE' inside section_patterns.
    """
    lines = text.split('\n')
    capture = False
    result = []
    for line in lines:
        # Normalize: strip '#' prefix and whitespace, then check if header matches
        normalized = line.strip().lstrip('#').strip()
        if normalized.upper().startswith(header.upper()):
            capture = True
            continue
        if capture and line.strip().startswith('#'):
            break
        if capture:
            result.append(line)
    return '\n'.join(result).strip()


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

    try:
        metrics = analyzer.get_context()
    except Exception as e:
        logger.warning("Metrics analyzer failed, using defaults: %s", e)
        metrics = str(DEFAULT_METRICS)

    # Extract high-signal sections from brand brain for focused injection
    # These are injected individually — we do NOT also inject the full metrics blob
    # to avoid duplicate context that wastes tokens and confuses the model
    generation_instructions = _extract_section(metrics, "GENERATION INSTRUCTIONS")
    signature_phrases       = _extract_section(metrics, "SIGNATURE CONSTRUCTIONS")
    brand_name              = _extract_section(metrics, "BRAND NAME")
    
    # Formulaic patterns
    opening_formula         = _extract_section(metrics, "OPENING PATTERN")
    closing_formula         = _extract_section(metrics, "CLOSING PATTERN")
    mechanical_rules        = _extract_section(metrics, "MECHANICAL RULES")
    evidence_anchoring      = _extract_section(metrics, "EVIDENCE PATTERN")
    diagnostic_style        = _extract_section(metrics, "DIAGNOSTIC STYLE")
    reframing_moves         = _extract_section(metrics, "REFRAMING MOVES")
    
    # New dimensions from improved extraction
    pronoun_pattern         = _extract_section(metrics, "PRONOUN PATTERN")
    qualification_style     = _extract_section(metrics, "QUALIFICATION STYLE")
    tone_signature          = _extract_section(metrics, "TONE SIGNATURE")

    # Fall back gracefully if sections are missing (cold start / sparse brain)
    if not generation_instructions:
        generation_instructions = "Write in first-person plural (we/our). Be direct and authoritative. Ground claims in specific experience and data."
    if not signature_phrases:
        signature_phrases = "None extracted yet — rely on brand voice metrics above."
    if not brand_name:
        brand_name = "our agency"
    
    # Fallbacks for formulaic patterns
    if not opening_formula:
        opening_formula = "Open with a relatable observation, pivot to brand authority, end with a contrast."
    if not closing_formula:
        closing_formula = "Close with brand methodology, parallel contrast, and soft CTA."
    if not mechanical_rules:
        mechanical_rules = "Use standard paragraph structure."
    if not evidence_anchoring:
        evidence_anchoring = "Ground claims in specific numbers, timeframes, or client outcomes."
    if not diagnostic_style:
        diagnostic_style = "Diagnose problems as intention failures, not surface symptoms."
    if not reframing_moves:
        reframing_moves = "Redefine concepts by negation and contrast."
    if not pronoun_pattern:
        pronoun_pattern = "First-person plural (we/our) as dominant voice."
    if not qualification_style:
        qualification_style = "Qualify with experience ('in our experience') rather than hedging ('might', 'could')."
    if not tone_signature:
        tone_signature = "Semi-formal, confident, authoritative but not aggressive."

    # RAG examples — injected as full voice reference only (no naive opening/closing extraction)
    try:
        examples = rag.query(topic)
        if not examples:
            examples = GENERIC_EXAMPLES
    except Exception as e:
        logger.warning("RAG failed, using generic examples: %s", e)
        examples = GENERIC_EXAMPLES

    # Learning memory — approved/rejected patterns with feedback reasoning
    try:
        patterns = memory.get_patterns(content_type)
    except Exception as e:
        logger.warning("Memory failed, using empty patterns: %s", e)
        patterns = DEFAULT_PATTERNS

    # Include feedback reasoning alongside angle labels (#14)
    approved_entries = patterns.get("approved", [])[:3]
    rejected_entries = patterns.get("rejected", [])[:2]
    
    approved_str = "\n".join(
        f"- {p['angle']}" + (f" (feedback: {p['feedback']})" if p.get('feedback') else "")
        for p in approved_entries
    ) if approved_entries else "None yet"
    
    rejected_str = "\n".join(
        f"- {p['angle']}" + (f" (reason: {p['feedback']})" if p.get('feedback') else "")
        for p in rejected_entries
    ) if rejected_entries else "None yet"

    if iteration == 1:
        prompt = WRITER_INITIAL.format(
            topic=topic,
            content_type=content_type,
            research=research,
            generation_instructions=generation_instructions,
            signature_phrases=signature_phrases,
            brand_name=brand_name,
            opening_formula=opening_formula,
            closing_formula=closing_formula,
            mechanical_rules=mechanical_rules,
            evidence_anchoring=evidence_anchoring,
            diagnostic_style=diagnostic_style,
            reframing_moves=reframing_moves,
            pronoun_pattern=pronoun_pattern,
            qualification_style=qualification_style,
            tone_signature=tone_signature,
            examples=examples,
            approved=approved_str,
            rejected=rejected_str
        )
    else:
        prompt = WRITER_REVISION.format(
            previous_content=state.get("content", ""),
            feedback=feedback,
            flagged_passages=state.get("flagged_passages", "No specific passages flagged."),
            style_match=state.get("style_match", 0.0),
            tone_match=state.get("tone_match", 0.0),
            structure_match=state.get("structure_match", 0.0),
            signature_match=state.get("signature_match", 0.0),
            generation_instructions=generation_instructions,
            signature_phrases=signature_phrases,
            brand_name=brand_name,
            opening_formula=opening_formula,
            closing_formula=closing_formula,
            mechanical_rules=mechanical_rules,
            evidence_anchoring=evidence_anchoring,
            diagnostic_style=diagnostic_style,
            reframing_moves=reframing_moves,
            pronoun_pattern=pronoun_pattern,
            qualification_style=qualification_style,
            tone_signature=tone_signature,
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