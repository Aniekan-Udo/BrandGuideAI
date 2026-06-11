# nodes/enforcer.py
#
# WHAT CHANGED FROM THE PREVIOUS VERSION:
#
# OLD: enforcer called analyzer.get_context() on every invocation,
#      hitting Redis (or worse, Postgres/rebuild) on every evaluation pass.
#      The raw text blob gave the enforcer no structured checklist to work from.
#
# NEW: enforcer reads brand_context dict directly from state.
#      The writer node already fetched and parsed it — no second lookup needed.
#      The enforcer now receives named sections (style_signature, opening_skeleton,
#      etc.) so it can evaluate against concrete, structured criteria rather than
#      scanning a flat text blob.
#
# The analyzer parameter is kept for backward compatibility with the LangGraph
# graph definition — but it is no longer used for context fetching.
# It can be removed once the graph wiring is updated.

import json
import logging
from model import LLMSingleton
from brand_metrics import BrandMetricsSQL
from prompts.enforcer import ENFORCER_PROMPT
from graph.state import GraphState

logger = logging.getLogger(__name__)

from utils.observe import observe


def _parse_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _build_enforcer_metrics(ctx: dict) -> str:
    """
    Assemble the structured brand context sections into a single
    formatted block for the enforcer prompt.

    The enforcer receives named sections with clear headers so it can
    evaluate each dimension against a concrete reference — not scan
    a flat synthesis blob looking for relevant information.
    """
    sections = [
        "# BRAND NAME",
        ctx.get("brand_name", "Not extracted"),

        "\n# VOICE OVERVIEW",
        ctx.get("brand_voice_overview", "Not available"),

        "\n# STYLE SIGNATURE",
        ctx.get("style_signature", "Not available"),

        "\n# TONE SIGNATURE",
        ctx.get("tone_signature", "Not available"),

        "\n# INTELLECTUAL PATTERNS",
        ctx.get("intellectual_patterns", "Not available"),

        "\n# OPENING SKELETON",
        ctx.get("opening_skeleton", "Not available"),

        "\n# CLOSING SKELETON",
        ctx.get("closing_skeleton", "Not available"),

        "\n# SIGNATURE CONSTRUCTIONS",
        ctx.get("signature_constructions", "Not available"),

        "\n# BRAND ASSET BANK",
        ctx.get("brand_asset_bank", "Not available"),

        "\n# GENERATION INSTRUCTIONS",
        "DO:\n" + ctx.get("generation_do", "Not available"),
        "\nDON'T:\n" + ctx.get("generation_dont", "Not available"),
    ]
    return "\n".join(sections)


@observe("enforcer_node")
def enforcer_node(state: GraphState, analyzer: BrandMetricsSQL) -> GraphState:
    content = state["content"]
    iteration = state.get("iteration", 1)
    max_iterations = 3

    # --- Read brand context from state (writer node already fetched this) ---
    ctx = state.get("brand_context", {})

    if not ctx:
        # Fallback: re-fetch if brand_context was not passed through state.
        # This should not happen in normal operation — log a warning so it's visible.
        logger.warning(
            "brand_context not found in state — falling back to analyzer.get_context(). "
            "Check that writer_node is setting brand_context in state."
        )
        raw_metrics = analyzer.get_context()
        # Use raw text as-is — structured parsing not available in fallback
        metrics_block = raw_metrics
    else:
        metrics_block = _build_enforcer_metrics(ctx)

    # --- Run enforcer LLM ---
    result = LLMSingleton.get().invoke(
        ENFORCER_PROMPT.format(
            metrics=metrics_block,
            content=content,
        )
    )

    logger.info("ENFORCER_RAW_OUTPUT:\n%s", result.content[:2000])

    # --- Parse evaluation ---
    try:
        evaluation = _parse_llm_json(result.content)
    except Exception:
        logger.error("Failed to parse enforcer output, defaulting to approve")
        evaluation = {
            "approved": True,
            "score": 7.0,
            "style_match": 0.0,
            "tone_match": 0.0,
            "structure_match": 0.0,
            "signature_match": 0.0,
            "fabrication_detected": False,
            "fabricated_claims": [],
            "feedback": "",
            "creative_angle": "unknown",
        }

    # --- Hard reject on fabrication regardless of other scores ---
    # Fabricated brand statistics destroy client trust instantly.
    if evaluation.get("fabrication_detected", False) and iteration < max_iterations:
        fabricated = evaluation.get("fabricated_claims", [])
        logger.warning(
            "Fabrication detected at iteration %d — forcing rejection. Claims: %s",
            iteration, fabricated,
        )
        evaluation["approved"] = False
        if not evaluation.get("feedback"):
            evaluation["feedback"] = (
                f"Fabricated statistics detected: {', '.join(fabricated)}. "
                "Remove these numbers entirely — do not replace with other invented figures. "
                "Only use numbers from the brand asset bank or research block."
            )

    # --- Force revision if score is below threshold and iterations remain ---
    # Prevents the enforcer from rubber-stamping weak first drafts.
    MIN_SCORE = 7.5
    if evaluation.get("score", 0.0) < MIN_SCORE and iteration < max_iterations:
        logger.info(
            "Score %.1f below threshold %.1f at iteration %d — forcing revision",
            evaluation["score"], MIN_SCORE, iteration,
        )
        evaluation["approved"] = False

        # Ensure feedback is populated so the writer knows what to fix.
        # Pull dimension-specific guidance from the brand context where possible.
        if not evaluation.get("feedback"):
            opening_hint = (
                f"Match this opening structure: {ctx.get('opening_skeleton', '')[:200]}"
                if ctx.get("opening_skeleton")
                else "Match the brand's opening pattern."
            )
            evaluation["feedback"] = (
                "Content does not sufficiently match the brand voice. "
                f"Focus on: {opening_hint}. "
                "Anchor every major claim to a specific number, timeframe, or outcome from the asset bank. "
                "Use first-person plural (we/our) throughout. "
                "Match the closing skeleton exactly. "
                "Weave in signature constructions naturally — do not force them."
            )

    # --- Hard cap — approve at max iterations regardless of score ---
    if not evaluation["approved"] and iteration >= max_iterations:
        logger.warning("Max iterations reached, forcing approval")
        evaluation["approved"] = True

    logger.info(
        "Enforcer: approved=%s score=%.1f style=%.1f tone=%.1f "
        "structure=%.1f signature=%.1f iteration=%d",
        evaluation["approved"],
        evaluation["score"],
        evaluation.get("style_match", 0.0),
        evaluation.get("tone_match", 0.0),
        evaluation.get("structure_match", 0.0),
        evaluation.get("signature_match", 0.0),
        iteration,
    )

    return {
        **state,
        "approved": evaluation["approved"],
        "score": evaluation["score"],
        "style_match": evaluation.get("style_match", 0.0),
        "tone_match": evaluation.get("tone_match", 0.0),
        "structure_match": evaluation.get("structure_match", 0.0),
        "signature_match": evaluation.get("signature_match", 0.0),
        "fabrication_detected": evaluation.get("fabrication_detected", False),
        "fabricated_claims": evaluation.get("fabricated_claims", []),
        "feedback": evaluation.get("feedback", ""),
        "creative_angle": evaluation.get("creative_angle", "unknown"),
        # Pass brand_context forward so revision node also has it
        "brand_context": ctx,
    }