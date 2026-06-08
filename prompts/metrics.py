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
      "sentence_rhythm": "<how the rhythm is mechanically achieved — e.g. 'alternates 3-8 word sentences with 12-20 word sentences; uses 1-2 sentence fragments per section for emphasis; no compound sentences longer than 25 words'>",
      "paragraph_constraints": "<mechanical constraints — e.g. 'max 4 sentences per paragraph; max 4 paragraphs per section; single-sentence paragraphs allowed for emphasis'>",
      "heading_format": "<exact heading format — e.g. 'numbered bold headings (1, 2, 3...) for main arguments; never bullet points for primary structure'>",
      "opening_mechanics": "<exact structural moves — e.g. 'relatable observation about common behavior → But here's the uncomfortable truth... pivot → one-sentence definition/contrast'>",
      "closing_mechanics": "<exact structural moves — e.g. 'brand methodology sentence → one parallel contrast statement (two short sentences) → soft CTA: Ready to [action]? Let's talk.'>",
      "evidence_anchoring": "<how claims are grounded — e.g. 'every major claim must have a specific number, timeframe, or client outcome'>"
    }}
  }},
  "intellectual_patterns": {{
  "diagnostic_style": "<how the brand diagnoses problems — e.g. 'brands confuse X with Y', 'brands perform rather than live', 'brands chase trends rather than build point of view'>",
  "value_hierarchy": "<what the brand prioritizes over what — e.g. 'consistency over creativity', 'authenticity over performance', 'relationship over transaction', 'intention over volume'>",
  "reframing_moves": "<how the brand redefines concepts — e.g. 'not creating content, creating noise', 'not a tactic, a strategy', 'not a transaction, a relationship'>",
  "authority_source": "<where the brand's authority comes from — e.g. '200 brands across industries', 'decade of crafting narratives', 'client outcomes over time'>",
  "argument_structure": "<how the brand builds arguments — e.g. 'relatable observation → pattern diagnosis → value hierarchy → prescription → outcome'>",
  "thinking_templates": [
    "<list 2-3 specific intellectual moves the brand makes — e.g. 'X isn't Y. It's Z.', 'The brands that win are the ones that...', 'We've seen brands [specific failure] — and then [outcome]. Why? Because [diagnosis].'>"
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
    "opening_formula": "<exact description of how this document opens — e.g. 'provocative truth statement that names a common mistake', 'question followed by immediate answer', 'brand experience claim with specific number'>",
    "closing_formula": "<exact description of how this document closes — e.g. 'one-line CTA as question: Ready to X? Lets Y.', 'punchy declarative kicker: Because X every time.', 'direct imperative'>",
    "section_pattern": "<description of how ideas are sequenced>",
    "narrative_arc": "<how the document builds: e.g. hook→problem→brand_experience→numbered_insights→CTA>",
    "invariant_templates": {{
      "opening_template": "<abstract the opening pattern with placeholders — replace brand names with [Brand Name], numbers with [number], specific claims with [specific claim]. Show the exact sequence of moves.>",
      "closing_template": "<abstract the closing pattern with placeholders — replace brand names with [Brand Name], actions with [action], outcomes with [outcome]. Show the exact sequence of moves.>",
      "section_template": "<abstract the section format with placeholders — show heading format, paragraph count, sentence count per paragraph, and the problem→solution rhythm.>"
    }}
  }},
  "persuasion": {{
    "primary_appeal": "<logos|ethos|pathos|mixed|none>",
    "social_proof_usage": "<none|light|heavy>",
    "social_proof_pattern": "<exact description of how social proof is used — e.g. 'specific client numbers: over 200 brands', 'timeframe anchors: a decade', 'outcome metrics: 500% traffic increase'>",
    "scarcity_or_urgency_tactics": <true|false>,
    "objection_handling": "<proactive|reactive|none>",
    "call_to_action_pattern": "<none|single|repeated|pervasive>",
    "cta_examples": ["<copy the exact CTA phrases from the document>"]
  }},
  "signature_patterns": [
    "<list of distinctive phrases, constructions, or habits unique to this document — copy exact phrases where possible>"
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
  "generation_instructions": "<a concrete, specific paragraph on how to write in this style. Name exact habits to replicate (e.g. open with a provocative truth, anchor every claim to a number, close with a one-line CTA). Name exact habits to avoid (e.g. never open with a rhetorical question, never use passive voice, never hedge with words like might or could).>"
}}


Content type: {content_type}
Document:
{document}"""

METRICS_SYNTHESIS = """You are a brand intelligence analyst. You have been given {total_documents} extracted style profiles from documents belonging to the same brand.

Your job is to synthesize these profiles into a single, precise brand intelligence brief that a content writer can use to produce new content that is indistinguishable from this brand's voice.

Rules:
- Where profiles agree, state the pattern confidently and concisely.
- Where profiles contradict, identify the underlying reason if possible (e.g. different content types, evolution over time) and give practical guidance on which to apply.
- Profiles with a higher weight (score_weight) represent validated high-quality content and should carry more influence. If weights are missing, treat all profiles equally.
- SIGNATURE PHRASES must include actual quoted phrases extracted from the documents — not descriptions of phrases. A writer must be able to read this section and know exactly what words to use.
- OPENING FORMULA and CLOSING FORMULA are the most critical sections. Be specific and concrete — describe the exact structural move the brand makes, and quote examples directly.
- OPENING TEMPLATE and CLOSING TEMPLATE must abstract the invariant pattern by replacing brand-specific words with [placeholders] like [Brand Name], [number], [specific claim], [action], [outcome]. Show the exact sequence of moves, not just a description.
- MECHANICAL RULES must state how each style quality is achieved mechanically — e.g. "punchy rhythm is achieved by alternating 3-8 word sentences with 12-20 word sentences and using 1-2 sentence fragments per section."
- GENERATION INSTRUCTIONS must be a concrete DO and DON'T brief. Every instruction must be specific enough that a writer can act on it immediately without interpretation.
- Do not invent patterns not present in the source profiles. If a dimension has insufficient data, state "Insufficient data" rather than guessing.
- Extract the brand name from the profiles if present and include it explicitly in the brief.

Business: {business_id}
Content type: {content_type}

Extracted profiles (ordered oldest to newest):
{profiles}

Return your synthesis as a well-structured plain text brand intelligence brief. Use clear section headers starting with #. Do not return JSON.

Structure your output exactly as follows:

# INTELLECTUAL PATTERNS
[How this brand thinks — not just how it sounds.]

DIAGNOSTIC STYLE:
[The lens the brand uses to see problems. e.g. "brands confuse activity with strategy," "brands perform values rather than live them," "brands chase trends rather than build point of view"]

VALUE HIERARCHY:
[What the brand prioritizes over what. e.g. "consistency > creativity," "authenticity > performance," "relationship > transaction," "intention > volume"]

REFRAMING MOVES:
[How the brand redefines concepts. e.g. "not creating content, creating noise," "not a transaction, a relationship," "not a tactic, the connective tissue"]

AUTHORITY SOURCE:
[Where the brand's credibility comes from. e.g. "200 brands across industries," "decade of crafting narratives," "specific client outcomes"]

ARGUMENT STRUCTURE:
[The intellectual arc of the brand's content. e.g. "relatable observation → pattern diagnosis → value hierarchy → prescription → outcome"]

THINKING TEMPLATES:
[Specific sentence structures the brand uses to make intellectual moves. e.g.]
- "X isn't Y. It's Z."
- "The brands that win are the ones that..."
- "We've seen brands [specific failure] — and then [outcome]. Why? Because [diagnosis]."
- "Most brands [common behavior]. But [reframe]."
- "[Activity] isn't [common definition]. It's [brand definition]."

# BRAND VOICE OVERVIEW
[2-3 sentence summary of the brand's core voice identity. Include the brand name if extracted.]

# BRAND NAME
[The brand name as extracted from documents. If not found, write: Not extracted — inject manually.]

# STYLE SIGNATURE
[Consolidated style rules with confidence levels. Include: sentence length, rhythm, voice, vocabulary level, formatting habits, numerical density.]

MECHANICAL RULES:
[For each style quality, state how it is mechanically achieved. Be specific and actionable.]
- Sentence rhythm: [how achieved — e.g. "alternates 3-8 word sentences with 12-20 word sentences; uses 1-2 sentence fragments per section for emphasis; no compound sentences longer than 25 words"]
- Paragraph constraints: [e.g. "max 4 sentences per paragraph; max 4 paragraphs per section; single-sentence paragraphs allowed for emphasis"]
- Heading format: [e.g. "numbered bold headings (1, 2, 3...) for main arguments; never bullet points for primary structure"]
- Evidence anchoring: [e.g. "every major claim must have a specific number, timeframe, or client outcome"]

# TONE SIGNATURE
[Consolidated tone rules with confidence levels. Include: register, assertiveness score, hedging frequency, emotional qualities, reader relationship.]

# STRUCTURE SIGNATURE
[Consolidated structural patterns. Include:]

OPENING FORMULA:
[Exact description of how this brand opens content. Quote 1-2 actual opening sentences from the profiles as examples.]

OPENING TEMPLATE:
[Abstract the invariant pattern with placeholders. Show the exact sequence of moves. Example: "[Relatable observation about common behavior: 'Every brand wants to be a publisher'] → [But here's the uncomfortable truth we tell every new client at [Brand Name]:] → [One-sentence definition/contrast that redefines the topic: 'most brands aren't creating content. They're creating noise.']"]

CLOSING FORMULA:
[Exact description of how this brand closes content. Quote 1-2 actual closing sentences from the profiles as examples.]

CLOSING TEMPLATE:
[Abstract the invariant pattern with placeholders. Example: "[Brand methodology sentence: At [Brand Name], we don't just... We help them...] → [Parallel contrast: two short sentences with identical structure: 'Content that doesn't just fill a feed. Content that fills a pipeline.'] → [Soft CTA: Ready to [action]? Let's talk.]"]

NARRATIVE ARC:
[The standard flow of ideas: e.g. provocative_truth → brand_experience_claim → problem_diagnosis → numbered_insights → CTA]

SECTION TEMPLATE:
[Abstract the section format with placeholders. Example: "Bold numbered heading (1, 2, 3...) → 2-4 paragraphs → each paragraph 2-4 sentences → first paragraph states problem, second paragraph states what winners do differently"]

EVIDENCE PATTERN:
[How the brand grounds claims — specific numbers, timeframes, client outcomes. Quote examples.]

# SIGNATURE PHRASES
Openings:
[Quoted phrases used to open content or sections]

Brand anchors:
[Quoted phrases that reference the brand by name or experience — e.g. "At Vantage Creative, we've..."]

List intros:
[Quoted phrases used to introduce lists or key points]

Closings:
[Quoted CTA phrases and closing kickers]

Emphasis constructions:
[Punctuation habits, em-dash usage, bold patterns, rhetorical constructions]

# GENERATION INSTRUCTIONS
DO:
- [Specific, actionable instruction]
- [Specific, actionable instruction]
(minimum 8 DO instructions)

DON'T:
- [Specific, actionable instruction]
- [Specific, actionable instruction]
(minimum 5 DON'T instructions)

# EDGE CASES & VARIATION
[When to deviate from the standard voice, if applicable]

# CONFIDENCE ASSESSMENT
[Which dimensions are well-established vs. need more data]"""