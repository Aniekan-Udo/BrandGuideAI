# nodes/writer_node.py
#
# HOW THIS CONNECTS TO brand_metrics.py
#
# The writer node no longer manually slices the raw synthesis string.
# It calls metrics.get_parsed_context() which returns a dict of named
# sections, then maps those directly into WRITER_INITIAL / WRITER_REVISION.
#
# This means:
#   - The writer always gets structured, named inputs — never a raw text blob
#   - If the brand context changes (new documents, re-synthesis), the writer
#     automatically picks up the new values on the next get_parsed_context() call
#   - Revision uses the same context dict — no duplication


from prompts.writer import WRITER_INITIAL, WRITER_REVISION
from brand_metrics import BrandMetricsSQL


def writer_node(state: dict) -> dict:
    """
    LangGraph writer node.

    Reads brand context via get_parsed_context(), maps it into
    WRITER_INITIAL, and writes the generated content back to state.

    State fields consumed:
        business_id     str
        content_type    str
        topic           str
        research        str   — from researcher node
        approved        str   — approved angles from previous enforcer runs
        rejected        str   — rejected angles from previous enforcer runs

    State fields produced:
        content         str   — generated content
        brand_context   dict  — parsed context dict, passed to enforcer
    """
    business_id = state["business_id"]
    content_type = state["content_type"]
    topic = state["topic"]
    research = state.get("research", "")
    approved = state.get("approved_angles", "")
    rejected = state.get("rejected_angles", "")

    # --- Load and parse brand context ---
    metrics = BrandMetricsSQL(business_id=business_id, content_type=content_type)
    ctx = metrics.get_parsed_context()

    if not ctx:
        # No brand context yet — cannot generate
        return {**state, "content": "", "error": "No brand context available. Upload documents first."}

    # --- Build the writer prompt ---
    prompt = WRITER_INITIAL.format(
        # Identity
        brand_name=ctx.get("brand_name", ""),
        content_type=content_type,
        topic=topic,

        # Block 1 — Brand Voice Brief
        voice_overview=ctx.get("brand_voice_overview", ""),
        intellectual_patterns=ctx.get("intellectual_patterns", ""),
        style_signature=ctx.get("style_signature", ""),
        tone_signature=ctx.get("tone_signature", ""),
        signature_constructions=ctx.get("signature_constructions", ""),

        # Block 2 — Structural Blueprint
        opening_skeleton=ctx.get("opening_skeleton", ""),
        section_pattern=ctx.get("section_pattern", ""),
        narrative_arc=ctx.get("narrative_arc", ""),
        closing_skeleton=ctx.get("closing_skeleton", ""),

        # Block 3 — Content Context
        asset_bank=ctx.get("brand_asset_bank", ""),
        research=research,
        approved=approved,
        rejected=rejected,

        # Generation instructions
        generation_do=ctx.get("generation_do", ""),
        generation_dont=ctx.get("generation_dont", ""),
    )

    # --- Call LLM ---
    from model import LLMSingleton
    llm = LLMSingleton.get("writer")
    result = llm.invoke(prompt)
    content = result.content.strip()

    return {
        **state,
        "content": content,
        "brand_context": ctx,   # pass parsed context to enforcer node
    }


def writer_revision_node(state: dict) -> dict:
    """
    LangGraph writer revision node.

    Called after enforcer rejects content. Uses WRITER_REVISION with
    the same brand context dict already in state — no second DB/cache read.

    State fields consumed (in addition to writer_node fields):
        content         str   — previous content to revise
        feedback        str   — enforcer feedback
        style_match     float
        tone_match      float
        structure_match float
        signature_match float
        brand_context   dict  — parsed context from writer_node

    State fields produced:
        content         str   — revised content
    """
    ctx = state.get("brand_context", {})

    if not ctx:
        # Fallback: re-fetch if brand_context was not passed through state
        metrics = BrandMetricsSQL(
            business_id=state["business_id"],
            content_type=state["content_type"],
        )
        ctx = metrics.get_parsed_context()

    prompt = WRITER_REVISION.format(
        # Scores and feedback
        style_match=state.get("style_match", 0.0),
        tone_match=state.get("tone_match", 0.0),
        structure_match=state.get("structure_match", 0.0),
        signature_match=state.get("signature_match", 0.0),
        feedback=state.get("feedback", ""),
        previous_content=state.get("content", ""),

        # Block 1 — Brand Voice Brief
        brand_name=ctx.get("brand_name", ""),
        voice_overview=ctx.get("brand_voice_overview", ""),
        intellectual_patterns=ctx.get("intellectual_patterns", ""),
        style_signature=ctx.get("style_signature", ""),
        tone_signature=ctx.get("tone_signature", ""),
        signature_constructions=ctx.get("signature_constructions", ""),

        # Block 2 — Structural Blueprint
        opening_skeleton=ctx.get("opening_skeleton", ""),
        section_pattern=ctx.get("section_pattern", ""),
        narrative_arc=ctx.get("narrative_arc", ""),
        closing_skeleton=ctx.get("closing_skeleton", ""),

        # Block 3 — Asset Bank
        asset_bank=ctx.get("brand_asset_bank", ""),

        # Generation instructions
        generation_do=ctx.get("generation_do", ""),
        generation_dont=ctx.get("generation_dont", ""),
    )

    from model import LLMSingleton
    llm = LLMSingleton.get("writer")
    result = llm.invoke(prompt)
    content = result.content.strip()

    return {**state, "content": content}