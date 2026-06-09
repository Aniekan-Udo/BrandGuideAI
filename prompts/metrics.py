# prompts/metrics.py

METRICS_EXTRACTION = """You are a document analyst. Analyze the document below and extract a precise style, tone, and structural profile that can be used to replicate its writing in new documents.

Return ONLY a JSON object with no preamble or markdown. Use this schema:
{{
  "brand_name": "<extract the brand or company name from the document. If not found, return null>",
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
    "numerical_density": "<low|medium|high>",
    "mechanical_rules": {{
      "sentence_rhythm": "<how rhythm is mechanically achieved — e.g. 'alternates 3-8 word sentences with 12-20 word sentences; uses 1-2 sentence fragments per section for emphasis'>",
      "paragraph_constraints": "<mechanical constraints — e.g. 'max 4 sentences per paragraph; single-sentence paragraphs allowed for emphasis'>",
      "heading_format": "<exact heading format — e.g. 'numbered bold headings (1, 2, 3...) for main arguments; never bullet points for primary structure'>",
      "opening_mechanics": "<exact structural moves — e.g. 'relatable observation → uncomfortable truth pivot → one-sentence contrast redefining the topic'>",
      "closing_mechanics": "<exact structural moves — e.g. 'brand methodology sentence → two short parallel contrast sentences → soft CTA question'>",
      "evidence_anchoring": "<how claims are grounded — e.g. 'every major claim must have a specific number, timeframe, or client outcome'>"
    }}
  }},
  "intellectual_patterns": {{
    "diagnostic_style": "<how the brand diagnoses problems — e.g. 'brands confuse activity with strategy', 'brands perform values rather than live them'>",
    "value_hierarchy": "<what the brand prioritizes over what — e.g. 'consistency over creativity', 'authenticity over performance', 'relationship over transaction'>",
    "reframing_moves": "<how the brand redefines concepts — e.g. 'not creating content, creating noise', 'not a tactic, the connective tissue'>",
    "authority_source": "<where the brand's authority comes from — e.g. 'over 200 brands across industries', 'a decade of crafting narratives'>",
    "argument_structure": "<how the brand builds arguments — e.g. 'relatable observation → pattern diagnosis → value hierarchy → prescription → outcome'>",
    "thinking_templates": [
      "<list 2-3 specific sentence structures the brand uses — e.g. 'X isn't Y. It's Z.', 'The brands that win are the ones that...', 'We've seen brands [failure] — and then [outcome]. Why? Because [diagnosis].'>"
    ]
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
    "opening_formula": "<exact description of how this document opens — e.g. 'relatable observation about common brand behavior followed by uncomfortable truth pivot anchored to brand experience'>",
    "closing_formula": "<exact description of how this document closes — e.g. 'one-line CTA as question: Ready to X? Let us Y.', 'punchy declarative kicker: Because X every time.'>",
    "section_pattern": "<description of how ideas are sequenced>",
    "narrative_arc": "<how the document builds — e.g. hook→problem→brand_experience→numbered_insights→CTA>"
  }},
  "persuasion": {{
    "primary_appeal": "<logos|ethos|pathos|mixed|none>",
    "social_proof_usage": "<none|light|heavy>",
    "social_proof_pattern": "<how social proof is used — e.g. 'specific client numbers: over 200 brands', 'timeframe anchors: a decade', 'outcome metrics: 500% traffic increase'>",
    "scarcity_or_urgency_tactics": <true|false>,
    "objection_handling": "<proactive|reactive|none>",
    "call_to_action_pattern": "<none|single|repeated|pervasive>",
    "cta_examples": ["<copy the exact CTA phrases from the document>"]
  }},
  "signature_patterns": [
    "<copy exact distinctive phrases, constructions, or habits from this document — quote verbatim where possible>"
  ],
  "opening_sentences": [
    "<copy the exact first 1-2 sentences of the document>"
  ],
  "closing_sentences": [
    "<copy the exact last 1-2 sentences of the document>"
  ],
  "section_signatures": {{
    "opening": "<exact pattern used to open — quote directly if under 20 words>",
    "list_intro": "<exact phrase used to introduce lists — e.g. 'Here are a few key takeaways:', 'Here is what we have learned:'>",
    "closing": "<exact pattern used to close>"
  }},
  "generation_instructions": "<a concrete, specific paragraph on how to write in this style. Name exact habits to replicate (e.g. open with a provocative truth, anchor every claim to a number, close with a one-line CTA). Name exact habits to avoid (e.g. never open with a rhetorical question, never hedge with might or could, never use passive voice).>"
}}

Content type: {content_type}
Document:
{document}"""


METRICS_SYNTHESIS = """You are a brand intelligence analyst. You have been given {total_documents} extracted style profiles from documents belonging to the same brand.

Your job is to synthesize these profiles into a single, precise brand intelligence brief that a content writer can use to produce new content that is indistinguishable from this brand's voice.

Rules:
- Where profiles agree, state the pattern confidently and concisely.
- Where profiles contradict, identify the underlying reason and give practical guidance on which to apply.
- Profiles with a higher weight (score_weight) represent validated high-quality content and should carry more influence.
- SIGNATURE PHRASES must include actual quoted phrases from the documents — not descriptions of phrases. A writer must be able to read this section and know exactly what words to use.
- OPENING FORMULA and CLOSING FORMULA are the most critical sections. Be specific — describe the exact structural move the brand makes and quote examples directly.
- GENERATION INSTRUCTIONS must be a concrete DO and DON'T brief. Every instruction must be specific enough that a writer can act on it immediately.
- Do not invent patterns not present in the source profiles. If a dimension has insufficient data, state "Insufficient data."
- Extract the brand name from the profiles if present and include it explicitly.

Business: {business_id}
Content type: {content_type}

Extracted profiles (ordered oldest to newest):
{profiles}

Return your synthesis as a well-structured plain text brand intelligence brief. Use clear section headers starting with #. Do not return JSON.

Structure your output exactly as follows:

# BRAND NAME
[The brand name extracted from documents. If not found, write: Not extracted — inject manually.]

# BRAND VOICE OVERVIEW
[2-3 sentence summary of the brand's core voice identity. Include the brand name.]

# INTELLECTUAL PATTERNS

DIAGNOSTIC STYLE:
[How this brand diagnoses problems. e.g. "brands confuse activity with strategy," "brands perform values rather than live them"]

VALUE HIERARCHY:
[What the brand prioritizes over what. e.g. "consistency > creativity," "authenticity > performance," "relationship > transaction"]

REFRAMING MOVES:
[How the brand redefines concepts. e.g. "not creating content, creating noise," "not a tactic, the connective tissue"]

AUTHORITY SOURCE:
[Where the brand's credibility comes from. e.g. "over 200 brands across industries," "a decade of crafting narratives"]

ARGUMENT STRUCTURE:
[The intellectual arc. e.g. "relatable observation → pattern diagnosis → value hierarchy → prescription → outcome"]

THINKING TEMPLATES:
[Specific sentence structures the brand uses. e.g.]
- "X isn't Y. It's Z."
- "The brands that win are the ones that..."
- "We've seen brands [specific failure] — and then [outcome]. Why? Because [diagnosis]."
- "Most brands [common behavior]. But [reframe]."

# STYLE SIGNATURE
[Consolidated style rules. Include: sentence length, rhythm, voice, vocabulary level, formatting habits, numerical density.]

MECHANICAL RULES:
- Sentence rhythm: [how achieved mechanically]
- Paragraph constraints: [specific limits]
- Heading format: [exact format]
- Evidence anchoring: [how claims are grounded]

# TONE SIGNATURE
[Consolidated tone rules. Include: register, assertiveness score, hedging frequency, emotional qualities, reader relationship.]

# STRUCTURE SIGNATURE

OPENING FORMULA:
[Exact description of how this brand opens content. Quote 1-2 actual opening sentences from the profiles.]

OPENING TEMPLATE:
[Abstract the invariant pattern with placeholders — e.g. "[Relatable observation] → [But here's the uncomfortable truth we tell every new client at [Brand Name]:] → [One-sentence contrast redefining the topic]"]

CLOSING FORMULA:
[Exact description of how this brand closes. Quote 1-2 actual closing sentences.]

CLOSING TEMPLATE:
[Abstract the invariant pattern — e.g. "[Brand methodology sentence] → [Parallel contrast: two short sentences] → [Soft CTA: Ready to [action]? Let's [action].]"]

NARRATIVE ARC:
[Standard flow — e.g. provocative_truth → brand_experience_claim → problem_diagnosis → numbered_insights → CTA]

EVIDENCE PATTERN:
[How the brand grounds claims — specific numbers, timeframes, client outcomes. Quote examples.]

# SIGNATURE PHRASES

Openings:
[Quoted phrases used to open content]

Brand anchors:
[Quoted phrases that reference the brand by name — e.g. "At Vantage Creative, we've..."]

List intros:
[Quoted phrases used to introduce lists]

Closings:
[Quoted CTA phrases and closing kickers]

Emphasis constructions:
[Em-dash usage, bold patterns, rhetorical constructions]

# GENERATION INSTRUCTIONS
DO:
- [Specific, actionable instruction — minimum 8]

DON'T:
- [Specific, actionable instruction — minimum 5]

# CONFIDENCE ASSESSMENT
[Which dimensions are well-established vs. need more data]"""