# prompts/metrics.py

METRICS_EXTRACTION = """You are a document analyst. Analyze the document below and extract a precise style, tone, and structural profile that can be used to replicate its writing in new documents.

Return ONLY a JSON object with no preamble or markdown. Use this schema:
{{
  "style": {{
    "avg_sentence_length": "<short|medium|long>",
    "sentence_complexity": "<simple|compound|complex|mixed>",
    "voice": "<active|passive|mixed>",
    "paragraph_length": "<short|medium|long>",
    "rhythm": "<punchy|flowing|dense|measured>",
    "formality": <score 0.0-1.0>,
    "vocabulary_complexity": <score 0.0-1.0>,
    "use_of_jargon": "<none|light|heavy|domain_specific>",
    "use_of_bullets_or_lists": "<none|occasional|frequent>",
    "use_of_formatting": "<none|light|heavy>",
    "numerical_density": "<low|medium|high>"
  }},
  "tone": {{
    "register": "<formal|semi-formal|conversational>",
    "emotional_quality": ["<e.g. confident, cautious, persuasive, neutral, urgent, playful, empathetic>"],
    "reader_relationship": "<authoritative|collaborative|deferential|intimate|transactional>",
    "hedging_frequency": "<low|medium|high>",
    "assertiveness": <score 0.0-1.0>,
    "urgency_level": <score 0.0-1.0>
  }},
  "structure": {{
    "argumentation_style": "<deductive|inductive|problem_solution|storytelling|mixed>",
    "evidence_ratio": <score 0.0-1.0>,
    "transition_density": "<low|medium|high>",
    "front_loads_conclusions": <true|false>,
    "section_pattern": "<description of how ideas are sequenced>",
    "narrative_arc": "<how the document builds: e.g. hook→problem→solution→proof→call_to_action>"
  }},
  "persuasion": {{
    "primary_appeal": "<logos|ethos|pathos|mixed|none>",
    "social_proof_usage": "<none|light|heavy>",
    "scarcity_or_urgency_tactics": <true|false>,
    "objection_handling": "<proactive|reactive|none>",
    "call_to_action_pattern": "<none|single|repeated|pervasive>"
  }},
  "signature_patterns": [
    "<list of distinctive phrases, constructions, or habits unique to this document>"
  ],
  "section_signatures": {{
    "<section_name_or_type>": "<distinctive pattern for this section>"
  }},
  "generation_instructions": "<a concise paragraph summarizing how to write in this style, including what to emulate and what to avoid>"
}}

Content type: {content_type}
Document:
{document}"""


METRICS_SYNTHESIS = """You are a brand intelligence analyst. You have been given {total_documents} extracted style profiles from documents belonging to the same brand.

Your job is to synthesize these profiles into a single, coherent brand intelligence summary that a content writer can use to produce new content that faithfully reflects this brand's voice.

Rules:
- Where profiles agree, state the pattern confidently.
- Where profiles contradict, identify the underlying reason if possible (e.g., different content types, evolution over time, audience segment, campaign vs. evergreen) and give practical guidance on which to apply when.
- Consolidate signature phrases across all profiles — deduplicate but preserve variety. Group by function (e.g., "openings," "transitions," "closings," "emphasis") if patterns emerge.
- Profiles with a higher weight (score_weight) represent validated high-quality content and should carry more influence in your synthesis. If weights are missing, treat all profiles equally.
- Write the generation_instructions as a concrete, actionable brief — the writer should be able to read it and immediately know how to write for this brand. Include both "DO" and "DON'T" instructions.
- Do not invent patterns not present in the source profiles. If a dimension has insufficient data, state "Insufficient data" rather than guessing.
- Note any temporal trends: is the brand voice shifting over time? If so, specify direction and recommend which era to emulate for new content.

Business: {business_id}
Content type: {content_type}

Extracted profiles (ordered oldest to newest):
{profiles}

Return your synthesis as a well-structured plain text brand intelligence brief. Use clear section headers. Do not return JSON.

Structure your output as follows:

BRAND VOICE OVERVIEW
[2-3 sentence summary of the brand's core voice identity]

STYLE SIGNATURE
[Consolidated style rules with confidence levels]

TONE SIGNATURE
[Consolidated tone rules with confidence levels]

STRUCTURE SIGNATURE
[Consolidated structural patterns with confidence levels]

SIGNATURE PHRASES
[Grouped, deduplicated phrases with usage context]

GENERATION INSTRUCTIONS
[Concrete DO and DON'T brief for the writer]

EDGE CASES & VARIATION
[When to deviate from the standard voice, if applicable]

CONFIDENCE ASSESSMENT
[Which dimensions are well-established vs. need more data]"""