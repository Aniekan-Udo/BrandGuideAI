# nodes/writer.py
import logging
from model import LLMSingleton
from brand_rag import BrandRAG
from learning_memory import FeedbackPortSQL
from brand_metrics import BrandMetricsSQL
from prompts.writer import WRITER_INITIAL, WRITER_REVISION
from graph.state import GraphState

logger = logging.getLogger(__name__)
import re
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



def _extract_asset_bank(metrics: str) -> str:
    """
    Extract the BRAND ASSET BANK section and format it as an explicit
    closed list of permitted claims for injection into the writer prompt.
    This prevents the writer from hallucinating client counts, percentages,
    and named frameworks by giving it only the facts it is allowed to use.
    """
    match = re.search(
        r"#\s*BRAND ASSET BANK\s*\n(.*?)(?=\n#\s+[A-Z]|\Z)",
        metrics,
        re.DOTALL | re.IGNORECASE
    )
    if not match:
        return (
            "No asset bank available yet. "
            "Do NOT invent specific numbers, client counts, percentages, or ROI figures. "
            "Use only general brand observations without specific data points."
        )
    asset_text = match.group(1).strip()
    return (
        "PERMITTED SOCIAL PROOF CLAIMS — use ONLY these exact numbers and facts when writing brand experience claims.\n"
        "Do NOT invent any number, percentage, client count, or framework name not listed here.\n\n"
        + asset_text
    )


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
    
    # Structural patterns — combine signature constructions + thinking templates
    # for a complete picture of the brand's canonical structural moves
    structural_patterns = _extract_section(metrics, "SIGNATURE CONSTRUCTIONS")
    thinking_templates  = _extract_section(metrics, "THINKING TEMPLATES")
    canonical_formula   = _extract_section(metrics, "CANONICAL STRUCTURAL FORMULA")
    if thinking_templates:
        structural_patterns = (structural_patterns + "\n\nTHINKING TEMPLATES:\n" + thinking_templates) if structural_patterns else thinking_templates
    if canonical_formula:
        structural_patterns = (structural_patterns + "\n\nCANONICAL STRUCTURAL FORMULA:\n" + canonical_formula) if structural_patterns else canonical_formula
    
    # New dimensions from improved extraction
    pronoun_pattern         = _extract_section(metrics, "PRONOUN PATTERN")
    qualification_style     = _extract_section(metrics, "QUALIFICATION STYLE")
    tone_signature          = _extract_section(metrics, "TONE SIGNATURE")

    # Extract permitted claims asset bank — passed explicitly to prevent hallucination
    asset_bank = _extract_asset_bank(metrics)

    # Fall back gracefully if sections are missing (cold start / sparse brain)
    if not generation_instructions:
        generation_instructions = "Write in first-person plural (we/our). Be direct and authoritative. Ground claims in specific experience and data."
    if not signature_phrases:
        signature_phrases = "None extracted yet — rely on brand voice metrics above."
    if not brand_name:
        brand_name = "our agency"
    
    # Fallbacks for formulaic patterns
    if not opening_formula:
        opening_formula = "No specific opening formula extracted. Write a natural, engaging opening appropriate for the topic."
    if not closing_formula:
        closing_formula = "No specific closing formula extracted. Write a natural closing appropriate for the topic."
    if not mechanical_rules:
        mechanical_rules = "Use standard paragraph structure."
    if not evidence_anchoring:
        evidence_anchoring = "Ground claims in specific numbers, timeframes, or client outcomes."
    if not diagnostic_style:
        diagnostic_style = "No specific diagnostic style extracted. Present problems clearly."
    if not reframing_moves:
        reframing_moves = "No specific reframing moves extracted. Explain concepts straightforwardly."
    if not pronoun_pattern:
        pronoun_pattern = "Use the appropriate pronoun perspective for the content type."
    if not qualification_style:
        qualification_style = "State claims clearly and confidently."
    if not tone_signature:
        tone_signature = "Professional and natural."
    if not structural_patterns:
        structural_patterns = "No structural patterns extracted yet — follow the opening/closing formulas and generation instructions above."

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
            structural_patterns=structural_patterns,
            pronoun_pattern=pronoun_pattern,
            qualification_style=qualification_style,
            tone_signature=tone_signature,
            examples=examples,
            approved=approved_str,
            rejected=rejected_str,
            asset_bank=asset_bank
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
            asset_bank=asset_bank
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