# prompts/extraction.py
#
# REVISED EXTRACTION PIPELINE v4 — Content-type agnostic.
# Fixes: lowered signature construction thresholds, explicit sentence-rhythm-to-function mapping,
# variant pattern elevation, and comprehensive thinking template extraction.
#
# PIPELINE:
#   PASS 0 — DOCUMENT INVENTORY
#   PASS 1 — STRUCTURAL DNA (with rejection criteria + specificity enforcement)
#   PASS 2 — BRAND ASSET BANK
#   PASS 2.5 — OPENING/CLOSING STRUCTURAL ABSTRACTION
#   PASS 3 — CROSS-DOCUMENT PATTERN CONSOLIDATION (with pattern elevation + variant detection)
#   PASS 4 — BEST EXAMPLE SELECTION
#   METRICS_SYNTHESIS


# ---------------------------------------------------------------------------
# PASS 0 — DOCUMENT INVENTORY & OPENING/CLOSING EXTRACTION
# ---------------------------------------------------------------------------

PASS0_DOCUMENT_INVENTORY = """You are a document structure analyst. Your job is to extract the literal opening and closing text blocks from this document, and classify its structural type.

WHAT YOU ARE EXTRACTING:
1. The verbatim opening — the first 1-3 paragraphs that establish the document's premise, tone, and reader relationship.
2. The verbatim closing — the final 1-3 paragraphs that resolve the argument and deliver the call-to-action or final statement.
3. The document's structural classification — what kind of rhetorical architecture this document uses.

RULES:
1. Extract opening and closing text VERBATIM. Do not paraphrase, summarize, or edit. Copy exactly as written.
2. If the document has no clear closing (e.g., an ad with only a headline and CTA button), extract what exists and mark it as truncated.
3. If the document has no opening (e.g., a proposal starting with "Scope of Work"), extract the first substantive block and note the absence of a traditional opening.

STRUCTURAL CLASSIFICATION OPTIONS (choose the closest match):
- "provocative_listicle": Numbered list of items with a provocative framing (e.g., "The 5 X That Actually Matter")
- "problem_reframe_essay": Identifies a common misconception, reframes it, then proves the reframe with evidence
- "diagnostic_manifesto": States an uncomfortable truth, diagnoses the root cause, prescribes a solution
- "case_study_narrative": Tells a specific client story with before/after and metrics
- "process_documentation": Describes a methodology or workflow step-by-step
- "comparison_framework": Compares two approaches and argues for one
- "authority_statement": Short, punchy declaration of expertise or position
- "social_proof_cluster": Dense collection of testimonials, metrics, or outcomes
- "cta_focused": Primarily a call-to-action with supporting rationale
- "other": Does not fit above — describe in your own words

Return ONLY a JSON object. No preamble, markdown, or explanation.

{{
  "brand_name": "<brand or company name extracted from document. null if not found>",
  "content_type": "<what kind of document this is — blog post, case study, agency overview, social post, proposal, ad, landing page, email sequence>",
  "structural_classification": "<provocative_listicle|problem_reframe_essay|diagnostic_manifesto|case_study_narrative|process_documentation|comparison_framework|authority_statement|social_proof_cluster|cta_focused|other>",
  "structural_classification_note": "<if 'other', explain. Otherwise, note any nuances>",

  "opening": {{
    "text_verbatim": "<first 1-3 paragraphs, copied exactly as written>",
    "word_count": <integer>,
    "sentence_count": <integer>,
    "has_hook": <true|false — does the opening contain a surprising claim, uncomfortable truth, or pattern interruption?>,
    "has_social_proof_anchor": <true|false — does it contain a credibility claim with numbers?>,
    "has_reframe": <true|false — does it redefine a common concept?>,
    "has_reader_address": <true|false — does it directly address the reader ("you", "your")?>
  }},

  "closing": {{
    "text_verbatim": "<final 1-3 paragraphs, copied exactly as written>",
    "word_count": <integer>,
    "sentence_count": <integer>,
    "has_cta": <true|false — does it contain a call to action?>,
    "has_reframe": <true|false — does it reframe the solution in memorable terms?>,
    "has_process_mention": <true|false — does it mention the brand's process or methodology?>,
    "has_soft_close": <true|false — does it use a question-based or low-pressure close?>,
    "truncated": <true|false — was there no clear closing to extract?>
  }},

  "body_structure_preview": {{
    "section_count": <integer — how many distinct sections/blocks in the body>,
    "section_types": ["<e.g. numbered_list, evidence_block, contrast_section, process_description, testimonial_cluster>"],
    "has_numbered_list": <true|false>,
    "has_bullet_list": <true|false>,
    "has_evidence_blocks": <true|false>,
    "has_contrast_sections": <true|false — sections that contrast bad vs. good approach>
  }}
}}

Document:
{document}"""


# ---------------------------------------------------------------------------
# PASS 1 — STRUCTURAL DNA EXTRACTION (v4)
# ---------------------------------------------------------------------------
# Key changes from v3:
# 1. signature_constructions: threshold lowered to >=50%, max 10, must detect ALL distinctive patterns
# 2. style.rhythm_pattern: sentence length MUST map to rhetorical function (not just "short and long")
# 3. style.paragraph_pattern: distinguishes opening, body, and closing paragraph patterns
# 4. intellectual_patterns.thinking_templates: extract ALL distinctive moves (>=2 docs), not just 3-5
# 5. Added SENTENCE-RHYTHM-TO-FUNCTION MAPPING RULE

PASS1_STRUCTURAL_DNA = """You are a writing pattern analyst. Your job is to extract HOW this document is written — the structural moves, rhythm patterns, and intellectual mechanics — in a form precise enough that a writer can replicate them on a completely different topic.

WHAT YOU ARE EXTRACTING:
Abstract, reusable writing patterns. Not what the document says. How it says things.

THREE RULES:
1. Never copy sentences, phrases, or specific words from the document.
2. For every pattern you name, provide a SKELETON that is SPECIFIC enough to prevent clichés.
3. A skeleton that uses ONLY generic placeholders like [CLAIM], [EXPLANATION], [EVIDENCE] is UNACCEPTABLE and will be rejected.

SKELETON QUALITY RULES — these are MANDATORY:
- Every sentence slot must describe the RHETORICAL FUNCTION in parentheses — e.g. "(uncomfortable truth stated as present-tense observation, no hedging)"
- Every sentence slot must specify APPROXIMATE LENGTH — e.g. "8-12 words" or "20-30 words"
- Every transition between sentences must describe the TRANSITION MECHANISM — e.g. "pivot with 'But here is what that actually means:'" or "contrast with 'Most [AUDIENCE] think [WRONG THING]. The reality is different.'"
- A writer following your skeleton should NOT be able to produce a generic or cliché result. The skeleton must force specificity.

BAD skeleton (reject this — too generic):
  "[CLAIM]. [EXPLANATION]. [EVIDENCE]."

GOOD skeleton (forces specificity):
  "[UNCOMFORTABLE TRUTH about what most [TARGET AUDIENCE] get wrong about [TOPIC] — stated as present-tense observation, no hedging, 8-12 words].
   [PIVOT using brand's direct experience — 'At [BRAND NAME], we've seen this in [SPECIFIC NUMBER] [CLIENT TYPE]' — 15-20 words].
   [REFRAME: split what [TARGET AUDIENCE] think [TOPIC] is from what it actually is in the brand's framework — two parallel clauses, 20-25 words total]."

REJECTION CRITERIA — the following outputs are UNACCEPTABLE and will be REJECTED:
- "Introduction to a problem" → replace with the SPECIFIC functional move (e.g., "pattern-interrupting uncomfortable truth", "authority-establishing social proof anchor")
- "Explanation of consequences" → replace with the SPECIFIC rhetorical mechanism (e.g., "diagnostic enumeration of hidden costs", "contrast between assumed and actual outcomes")
- "Offer of a solution" → replace with the SPECIFIC transition pattern (e.g., "process mention that reframes the brand as diagnostician", "value reframe that splits old approach from new framework")
- "Evidence of effectiveness" → replace with the SPECIFIC evidence pattern (e.g., "social proof block with exact client count and percentage outcome", "before/after metric comparison")
- Any description using generic consulting language: "frames problems as opportunities", "uses a solutions-focused approach", "emphasizes specificity and clarity"
- Any description that could apply to ANY brand: "uses evidence to support claims", "maintains an authoritative tone", "uses a clear structure"
- Any argument structure described as "introduction, body, conclusion" or "problem, evidence, solution, CTA"
- Any sentence rhythm described as "a mix of short and long sentences" without mapping length to rhetorical function
- Any paragraph pattern that does not distinguish opening, body, and closing paragraph structures

PATTERN SPECIFICITY RULES:
- For every pattern, you MUST name the EXACT MECHANISM: the specific syntactic move, the specific transition type, the specific sentence rhythm.
- If a pattern uses negation, say "tripartite negation-reframe: [X] isn't [Y]. It isn't [Z]. It's [W]."
- If a pattern uses social proof, say "embedded social proof anchor with exact client count and outcome percentage"
- If a pattern uses contrast, say "parallel contrast with 'doesn't just [X]. [Y] that [Z].'"
- If you cannot identify the specific mechanism, write "MECHANISM NOT IDENTIFIED — insufficient data" rather than inventing a generic description.

SENTENCE-RHYTHM-TO-FUNCTION MAPPING RULE:
The rhythm_pattern description MUST map specific sentence lengths to specific rhetorical functions.
Do NOT say "short sentences for punch, long sentences for evidence." Say:
- "Ultra-short punch (4-8 words): uncomfortable truth or reframe stated bluntly"
- "Medium evidence (15-20 words): social proof block with exact client count and outcome percentage"
- "Long elaboration (25-35 words): tripartite negation or parallel contrast with full clause structure"
- "Short close (8-12 words): result reframe or soft CTA"
The skeleton must reflect this length-to-function mapping exactly.

SIGNATURE CONSTRUCTION DETECTION RULE:
A construction is signature if it uses a distinctive syntactic pattern that a writer
could not produce by accident. Extract ALL such constructions you detect in this
document, up to 10. Do not limit yourself to 4-6. If the document has 8 distinctive
constructions, extract all 8. Include frequency for each.

THINKING TEMPLATE DETECTION RULE:
Extract EVERY distinctive sentence-level move that appears in this document.
There is no minimum or maximum. If the document has 10 distinctive thinking templates,
extract all 10. Each must have a specific mechanism name and a skeleton.

CONTENT TYPE CONTEXT:
This is a {content_type} with structural classification: {structural_classification}.
When extracting patterns, consider what this content type typically does and how THIS document deviates from or exceeds those conventions.

Return ONLY a JSON object. No preamble, markdown, or explanation.

{{
  "brand_name": "<brand or company name extracted from document. null if not found>",
  "content_type": "<what kind of document this is>",
  "structural_classification": "<from Pass 0>",

  "canonical_formula": {{
    "detected": <true|false — does this document follow a clear, repeated formula?>,
    "description": "<if true, describe the formula as a sequence of SPECIFIC FUNCTIONAL MOVES. Use the exact move names from the rejection criteria rules. If false, write 'No single formula detected'>",
    "move_sequence": [
      "<Move 1: specific functional description using exact mechanism names — e.g. 'pattern-interrupting uncomfortable truth stated as present-tense observation'>",
      "<Move 2: e.g. 'authority-establishing social proof anchor with exact client count and outcome percentage'>",
      "<Move 3: e.g. 'tripartite negation-reframe that redefines the concept using [X] isn't [Y]. It isn't [Z]. It's [W].'>",
      "<Move 4: e.g. 'numbered diagnostic section with embedded social proof blocks'>",
      "<Move 5: e.g. 'process mention transition that reframes brand as diagnostician'>",
      "<Move 6: e.g. 'parallel contrast result reframe using doesn't just [X]. [Y] that [Z].'>",
      "<Move 7: e.g. 'soft CTA using question-based invitation'>",
      "..."
    ],
    "skeleton": "<if detected, provide a full-document skeleton following the quality rules above. This is the highest-priority output.>"
  }},

  "style": {{
    "avg_sentence_length": "<short|medium|long>",
    "sentence_complexity": "<simple|compound|complex|mixed>",
    "voice": "<active|passive|mixed>",
    "paragraph_length": "<short 1-2 sentences|medium 3-4 sentences|long 5+ sentences>",
    "formality": <0.0-1.0>,
    "vocabulary_complexity": <0.0-1.0>,
    "use_of_jargon": "<none|light|heavy|domain_specific>",
    "use_of_bullets_or_lists": "<none|occasional|frequent>",
    "numerical_density": "<low|medium|high>",

    "rhythm_pattern": {{
      "description": "<describe the sentence rhythm mechanics using the SENTENCE-RHYTHM-TO-FUNCTION MAPPING RULE. Map specific lengths to specific rhetorical functions. Be exact about word counts and what each length DOES.>",
      "skeleton": "<reconstruct the rhythm as a structural frame using placeholders, following the quality rules and the length-to-function mapping>"
    }},

    "paragraph_pattern": {{
      "opening_paragraph": {{
        "description": "<describe the opening paragraph structure — how many sentences, what role each sentence plays. Use exact mechanism names.>",
        "skeleton": "<reconstruct the opening paragraph as a structural frame>"
      }},
      "body_paragraph": {{
        "description": "<describe the body paragraph structure — how many sentences, what role each sentence plays. Use exact mechanism names.>",
        "skeleton": "<reconstruct a typical body paragraph as a structural frame>"
      }},
      "closing_paragraph": {{
        "description": "<describe the closing paragraph structure — how many sentences, what role each sentence plays. Use exact mechanism names.>",
        "skeleton": "<reconstruct the closing paragraph as a structural frame>"
      }}
    }},

    "evidence_anchoring_rule": {{
      "description": "<describe the rule for how claims are grounded — the EXACT SYNTACTIC PATTERN. Not 'uses numbers' but 'embeds social proof using past-tense action + specific client count + outcome percentage in a single compound sentence'>",
      "skeleton": "<reconstruct a typical evidence-anchored claim as a structural frame, following the quality rules>"
    }}
  }},

  "intellectual_patterns": {{
    "diagnostic_style": {{
      "description": "<HOW the brand names and frames problems — the EXACT MECHANISM. Not 'they identify problems' but the specific pattern: do they use tripartite negation? embedded contrast? analogy? data-driven enumeration? Name the exact move.>",
      "skeleton": "<reconstruct the diagnostic move as a structural frame, following the quality rules>"
    }},
    "reframing_move": {{
      "description": "<HOW the brand redefines concepts — the EXACT MECHANISM. Not 'they reframe' but the specific pattern: do they use 'X isn't Y, it's Z'? do they use parallel contrast? do they use authority-based redefinition? Name the exact move.>",
      "skeleton": "<reconstruct the reframing move as a structural frame, following the quality rules>"
    }},
    "argument_structure": {{
      "description": "<the intellectual arc — describe as a sequence of SPECIFIC FUNCTIONAL MOVES. Use exact mechanism names. Do NOT use generic stage names like 'introduction' or 'body'>",
      "sequence": [
        "<Move 1: specific functional description using exact mechanism names>",
        "<Move 2: e.g. 'authority-establishing social proof anchor with exact numbers'>",
        "<Move 3: e.g. 'tripartite negation-reframe using [X] isn't [Y] pattern'>",
        "<Move 4 if present>"
      ]
    }},
    "thinking_templates": [
      {{
        "description": "<describe the intellectual move — what it DOES structurally, using exact mechanism names. Not 'uses examples' but 'embeds social proof using past-tense action + specific client count + outcome percentage'>",
        "skeleton": "<reconstruct the move as a structural frame, following the quality rules>"
      }}
    ]
  }},

  "tone": {{
    "register": "<formal|semi-formal|conversational>",
    "emotional_quality": ["<e.g. confident, direct, empathetic, urgent>"],
    "reader_relationship": "<authoritative|collaborative|deferential|intimate|transactional>",
    "assertiveness": <0.0-1.0>,
    "hedging_frequency": "<low|medium|high>",
    "urgency_level": <0.0-1.0>
  }},

  "structure": {{
    "argumentation_style": "<deductive|inductive|problem_solution|storytelling|mixed>",
    "front_loads_conclusions": <true|false>,
    "transition_density": "<low|medium|high>",
    "evidence_ratio": <0.0-1.0>,
    "narrative_arc": {{
      "description": "<the overall flow described as a sequence of SPECIFIC FUNCTIONAL MOVES. Use exact mechanism names. Be specific: 'pattern-interrupting uncomfortable truth → authority-establishing social proof anchor → tripartite negation-reframe → numbered diagnostic sections with embedded social proof blocks → process mention transition → parallel contrast result reframe → soft CTA'>",
      "sequence": [
        "<Move 1: specific functional description using exact mechanism names>",
        "<Move 2>",
        "<Move 3>",
        "..."
      ]
    }}
  }},

  "persuasion": {{
    "primary_appeal": "<logos|ethos|pathos|mixed>",
    "social_proof_usage": "<none|light|heavy>",
    "social_proof_pattern": {{
      "description": "<HOW social proof is deployed — the EXACT MECHANISM. Not 'they use numbers' but the specific pattern: do they lead with it? embed it in evidence blocks? cluster it? Name the exact syntactic pattern.>",
      "skeleton": "<reconstruct a social proof sentence as a structural frame, following the quality rules>"
    }},
    "cta_pattern": {{
      "present": <true|false>,
      "description": "<HOW the CTA is written — the EXACT MECHANISM. Is it a question-based soft close? A command? A conditional invitation? Name the exact pattern.>",
      "skeleton": "<reconstruct the CTA as a structural frame, following the quality rules>"
    }}
  }},

  "signature_constructions": [
    {{
      "description": "<describe WHAT THIS CONSTRUCTION DOES — the EXACT RHETORICAL OR STRUCTURAL MOVE. Extract ALL distinctive constructions up to 10. These must be DISTINCT, NON-GENERIC, and NAMED USING EXACT MECHANISMS.>",
      "skeleton": "<reconstruct the construction as a structural frame, following the quality rules>",
      "frequency": "<how often this construction appears in the document: once|occasional|frequent|ubiquitous>"
    }}
  ],

  "generation_instructions": {{
    "do": [
      "<concrete pattern-based instruction using EXACT MECHANISM NAMES. minimum 8. Each must be specific enough that a writer knows exactly what syntactic move to execute. NOT 'use evidence' but 'anchor every claim with a social proof block using past-tense action + specific client count + outcome percentage'>",
      "<NOT 'use a clear structure' but 'open with a pattern-interrupting uncomfortable truth stated as present-tense observation with no hedging'>"
    ],
    "dont": [
      "<concrete anti-pattern instruction using EXACT MECHANISM NAMES. minimum 5. Each must explain the negative consequence. NOT 'avoid vague language' but 'do not open with a question — the brand uses blunt present-tense observations, not interrogative hooks'>",
      "<NOT 'avoid passive voice' but 'do not use hedging language like 'might', 'could', or 'perhaps' — the brand states uncomfortable truths directly' >"
    ]
  }}
}}

Content type: {content_type}
Structural classification: {structural_classification}

Document:
{document}"""


# ---------------------------------------------------------------------------
# PASS 2 — BRAND ASSET BANK EXTRACTION (UNCHANGED)
# ---------------------------------------------------------------------------

PASS2_ASSET_BANK = """You are a brand fact extractor. Your job is to pull every specific, verifiable brand asset from this document — the raw facts, numbers, named frameworks, stated values, and concrete claims that belong to this brand.

WHAT YOU ARE EXTRACTING:
Specific brand-owned facts. Exact numbers. Named methodologies. Stated beliefs. Concrete outcomes.
These are the evidence anchors a writer injects into new content to make it sound like it comes from a real brand with real experience — not a generic AI.

RULES:
1. Extract facts EXACTLY as stated. Do not paraphrase or abstract them.
2. If a fact includes a number, keep the number exactly.
3. If a fact includes a timeframe, keep the timeframe exactly.
4. If a claim is vague (e.g. "many clients"), mark it as low_confidence.
5. Do not invent, infer, or fill in gaps. Only extract what is explicitly stated.

Return ONLY a JSON object. No preamble, markdown, or explanation.

{{
  "brand_name": "<brand or company name. null if not found>",
  "content_type": "<what kind of document this is>",

  "social_proof_assets": [
    {{
      "claim": "<exact claim as stated in document>",
      "type": "<client_count|outcome_metric|timeframe|testimonial|award|other>",
      "confidence": "<high|medium|low>",
      "note": "<optional: any context needed to use this asset correctly>"
    }}
  ],

  "named_frameworks_or_methodologies": [
    {{
      "name": "<exact name as used in document>",
      "description": "<what it is, in the brand's own terms>",
      "how_to_reference": "<how to naturally mention this in new content>"
    }}
  ],

  "stated_values_or_beliefs": [
    {{
      "belief": "<the stated belief or value>",
      "priority": "<high|medium|low — based on how prominently it appears>",
      "how_brand_expresses_it": "<how this belief typically shows up in the writing>"
    }}
  ],

  "brand_positioning_claims": [
    {{
      "claim": "<exact positioning claim>",
      "claim_type": "<differentiator|category_definition|mission|vision|promise>",
      "confidence": "<high|medium|low>"
    }}
  ],

  "industry_or_domain_vocabulary": [
    "<specific terms, phrases, or domain language this brand uses that are distinctive or recurring>"
  ],

  "explicit_client_or_audience_descriptors": [
    "<how the brand describes its clients or target audience — exact terms used>"
  ],

  "content_topics_covered": [
    "<the subjects and themes this document addresses — helps map what the brand talks about>"
  ]
}}

Content type: {content_type}

Document:
{document}"""


# ---------------------------------------------------------------------------
# PASS 2.5 — OPENING/CLOSING STRUCTURAL ABSTRACTION (UNCHANGED)
# ---------------------------------------------------------------------------

PASS25_OPENING_CLOSING_ABSTRACTION = """You are a structural abstraction analyst. Your job is to convert a document's literal opening and closing into a pure structural representation — a sequence of rhetorical moves with no content-specific words.

WHAT YOU RECEIVE:
- The verbatim opening and closing text from the document
- The document's structural classification and structural DNA from Pass 1

WHAT YOU PRODUCE:
For the opening:
  1. A move_sequence: what each sentence DOES functionally (not what it says)
  2. A skeleton: the structural frame using ONLY generic placeholders, with
     rhetorical function descriptions, length constraints, and transition mechanisms
  3. A topic_independence_score: 0-10 — how replicable this structure is to
     a completely different topic (10 = fully replicable, 0 = topic-locked)

For the closing:
  Same three outputs.

CRITICAL RULES:
1. NEVER copy words, phrases, numbers, or brand names from the source text.
2. The skeleton must be so abstract that applying it to "accounting software"
   or "vegan meal kits" produces equally valid results.
3. If the opening contains a specific topic hook (e.g., "pricing"), the skeleton
   must use [TOPIC] — not [PRICING], [MARKETING], [RETENTION], etc.
4. If the opening contains brand-specific social proof, the skeleton must use
   [BRAND NAME] and [SPECIFIC NUMBER] — never the actual numbers.
5. Score topic_independence harshly. If the structure only works because of
   the original topic, score it 0-3. If the moves are fully transferable, 8-10.
6. Do not describe the CONTENT of the moves. Describe the STRUCTURAL FUNCTION.
   BAD: "Introduces the pricing problem"
   GOOD: "States an uncomfortable truth about a common misconception that the
          target audience holds about the topic, using present-tense observation
          with no hedging"

SKELETON QUALITY RULES (same as Pass 1):
- Every sentence slot: (rhetorical function in parentheses)
- Every sentence slot: approximate word count
- Every transition: described mechanism
- No generic [CLAIM], [EXPLANATION], [EVIDENCE] placeholders

BAD:
  "[HOOK about TOPIC]. [EXPLANATION of problem]. [EVIDENCE from experience]."

GOOD:
  "[UNCOMFORTABLE TRUTH about what most [TARGET AUDIENCE] misunderstand
   about [TOPIC] — stated as present-tense observation, no hedging, 8-12 words].
   [PIVOT to brand authority — 'At [BRAND NAME], we've [ACTION] [NUMBER]
   [CLIENT TYPE]' — 15-20 words].
   [TRIPARTITE NEGATION: [TOPIC] isn't [COMMON MISCONCEPTION 1]. It isn't
   [COMMON MISCONCEPTION 2]. It's [BRAND FRAMEWORK], and most [AUDIENCE]
   treat it like [WRONG APPROACH] — 25-35 words total]."

Return ONLY a JSON object. No preamble, markdown, or explanation.

{{
  "document_index": {document_index},
  "content_type": "{content_type}",
  "structural_classification": "{structural_classification}",

  "opening_abstraction": {{
    "move_sequence": [
      "<Move 1: functional description, no content references>",
      "<Move 2>",
      "<Move 3>"
    ],
    "skeleton": "<pure structural skeleton, following quality rules>",
    "topic_independence_score": <0-10>,
    "why": "<one sentence: why this score, what makes it transferable or locked>"
  }},

  "closing_abstraction": {{
    "move_sequence": [
      "<Move 1: functional description>",
      "<Move 2>",
      "<Move 3>"
    ],
    "skeleton": "<pure structural skeleton>",
    "topic_independence_score": <0-10>,
    "why": "<one sentence>"
  }}
}}

Verbatim opening:
{opening_verbatim}

Verbatim closing:
{closing_verbatim}

Structural DNA from Pass 1:
{structural_dna}"""


# ---------------------------------------------------------------------------
# PASS 3 — CROSS-DOCUMENT PATTERN CONSOLIDATION (v4)
# ---------------------------------------------------------------------------
# Key changes from v3:
# 1. Added NEAR-CANONICAL confidence level (50-60% prevalence)
# 2. signature_constructions_consolidated: includes near-canonical patterns
# 3. thinking_templates_consolidated: new section for sentence-level moves
# 4. Added PARAGRAPH PATTERN consolidation (opening, body, closing)

PASS3_PATTERN_CONSOLIDATION = """You are a cross-document pattern analyst. You have been given {total_documents} STRUCTURAL DNA profiles extracted from documents belonging to the same brand.

Your job is to compare these profiles and identify which patterns are CANONICAL (shared across most documents), which are NEAR-CANONICAL (shared across half), which are VARIANTS (content-type-specific), and which are UNIQUE (one-off).

CONSOLIDATION RULES:
1. A pattern is CANONICAL if it appears in >= 60% of documents (e.g., 6+ out of 10). These become the brand's core voice.
2. A pattern is NEAR-CANONICAL if it appears in >= 50% but < 60% of documents. These are likely canonical but need more data to confirm. Include them with a note.
3. A pattern is VARIANT if it appears in >= 2 documents but < 50%. These are valid but content-type-specific.
4. A pattern is UNIQUE if it appears in only 1 document. Flag these as low-confidence unless they are exceptionally distinctive.
5. For each canonical and near-canonical pattern, select the BEST skeleton from the documents that exhibit it.
6. If a pattern is described differently across documents but is clearly the SAME pattern, unify the description and select the best skeleton.
7. If documents contradict on a dimension, note the contradiction and identify which documents drive each position.

PATTERN ELEVATION RULE:
When a pattern is elevated to CANONICAL or NEAR-CANONICAL status, you MUST preserve
the SPECIFICITY of the best individual document's description. Do NOT water it down
to generic language just because it appears across multiple documents.

REJECTION CRITERIA for consolidation output:
- "Introduction to a problem" → replace with specific functional move
- "Explanation of consequences" → replace with specific rhetorical mechanism
- "Offer of a solution" → replace with specific transition pattern
- "Evidence of effectiveness" → replace with specific evidence pattern
- Any generic consulting language: "frames problems as opportunities", "uses a solutions-focused approach"
- Any description that could apply to ANY brand
- Any argument structure using generic stage names: "introduction, body, conclusion"
- Any sentence rhythm described as "a mix of short and long sentences" without mapping length to function

SPECIFICITY ENFORCEMENT:
- For canonical patterns, use the EXACT MECHANISM NAMES from the individual profiles
- If 7/10 documents use "tripartite negation-reframe", the canonical description MUST say "tripartite negation-reframe", not "reframing move"
- If 5/10 documents use "process mention transition", it is NEAR-CANONICAL — include it with that label
- The canonical skeleton should be the BEST individual skeleton, not a diluted average

PATTERN TYPES TO CONSOLIDATE:
- canonical_formula (from Pass 1): Does a shared formula exist across documents?
- rhythm_pattern: Is there a consistent sentence rhythm with length-to-function mapping?
- paragraph_pattern (opening, body, closing): Are there consistent paragraph architectures?
- evidence_anchoring_rule: Is there a consistent way claims are grounded?
- diagnostic_style: Is there a consistent way problems are framed?
- reframing_move: Is there a consistent way concepts are redefined?
- argument_structure: Is there a consistent intellectual arc?
- social_proof_pattern: Is there a consistent way social proof is deployed?
- cta_pattern: Is there a consistent CTA architecture?
- signature_constructions: Which constructions appear across multiple documents?
- thinking_templates: Which sentence-level moves appear across multiple documents?
- tone dimensions: Are register, assertiveness, hedging consistent?
- narrative_arc: Is there a consistent overall flow?

For each pattern type, output:
- confidence: <canonical|near_canonical|variant|unique|insufficient_data>
- prevalence: <X out of Y documents>
- canonical_description: <unified description using EXACT MECHANISM NAMES>
- canonical_skeleton: <best skeleton from the set, following quality rules>
- variant_notes: <if variant, which content types use which version>
- contradiction_notes: <if contradictions exist, explain them>

Return ONLY a JSON object. No preamble, markdown, or explanation.

{{
  "brand_name": "<brand name from documents>",
  "total_documents_analyzed": {total_documents},

  "canonical_patterns": {{
    "canonical_formula": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "rhythm_pattern": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES with length-to-function mapping>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "paragraph_pattern": {{
      "opening_paragraph": {{
        "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
        "prevalence": "<X/Y>",
        "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
        "canonical_skeleton": "<best skeleton>",
        "variant_notes": "<if applicable>"
      }},
      "body_paragraph": {{
        "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
        "prevalence": "<X/Y>",
        "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
        "canonical_skeleton": "<best skeleton>",
        "variant_notes": "<if applicable>"
      }},
      "closing_paragraph": {{
        "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
        "prevalence": "<X/Y>",
        "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
        "canonical_skeleton": "<best skeleton>",
        "variant_notes": "<if applicable>"
      }}
    }},
    "evidence_anchoring_rule": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "diagnostic_style": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "reframing_move": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "argument_structure": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_sequence": ["<Move 1>", "<Move 2>", "<Move 3>", "..."],
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "social_proof_pattern": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "cta_pattern": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }},
    "narrative_arc": {{
      "confidence": "<canonical|near_canonical|variant|unique|insufficient_data>",
      "prevalence": "<X/Y>",
      "canonical_description": "<unified description using EXACT MECHANISM NAMES>",
      "canonical_sequence": ["<Move 1>", "<Move 2>", "<Move 3>", "..."],
      "variant_notes": "<if applicable>",
      "contradiction_notes": "<if applicable>"
    }}
  }},

  "signature_constructions_consolidated": [
    {{
      "construction_name": "<descriptive name using EXACT MECHANISM NAMES>",
      "confidence": "<canonical|near_canonical|variant|unique>",
      "prevalence": "<X/Y>",
      "canonical_description": "<what it does using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "appears_in_content_types": ["<list of content types where this appears>"]
    }}
  ],

  "thinking_templates_consolidated": [
    {{
      "template_name": "<descriptive name using EXACT MECHANISM NAMES>",
      "confidence": "<canonical|near_canonical|variant|unique>",
      "prevalence": "<X/Y>",
      "canonical_description": "<what it does using EXACT MECHANISM NAMES>",
      "canonical_skeleton": "<best skeleton>",
      "appears_in_content_types": ["<list of content types where this appears>"]
    }}
  ],

  "tone_consolidation": {{
    "register": {{
      "canonical_value": "<formal|semi-formal|conversational>",
      "confidence": "<canonical|near_canonical|variant|unique>",
      "prevalence": "<X/Y>",
      "variant_notes": "<if different content types use different registers>"
    }},
    "assertiveness": {{
      "canonical_value": <0.0-1.0>,
      "confidence": "<canonical|near_canonical|variant|unique>",
      "range": "<min-max across documents>",
      "variant_notes": "<if applicable>"
    }},
    "hedging_frequency": {{
      "canonical_value": "<low|medium|high>",
      "confidence": "<canonical|near_canonical|variant|unique>",
      "prevalence": "<X/Y>",
      "variant_notes": "<if applicable>"
    }},
    "reader_relationship": {{
      "canonical_value": "<authoritative|collaborative|deferential|intimate|transactional>",
      "confidence": "<canonical|near_canonical|variant|unique>",
      "prevalence": "<X/Y>",
      "variant_notes": "<if applicable>"
    }}
  }},

  "generation_instructions_consolidated": {{
    "do": [
      "<consolidated instruction using EXACT MECHANISM NAMES — must be canonical or near-canonical. minimum 8. NOT 'use evidence' but 'anchor every claim with a social proof block using past-tense action + specific client count + outcome percentage'>",
      "<NOT 'use a clear structure' but 'open with a pattern-interrupting uncomfortable truth stated as present-tense observation with no hedging'>"
    ],
    "dont": [
      "<consolidated anti-pattern using EXACT MECHANISM NAMES — must be canonical or near-canonical. minimum 5. NOT 'avoid vague language' but 'do not open with a question — the brand uses blunt present-tense observations, not interrogative hooks'>",
      "<NOT 'avoid passive voice' but 'do not use hedging language like 'might', 'could', or 'perhaps' — the brand states uncomfortable truths directly' >"
    ],
    "variant_do": [
      "<instruction that is valid but content-type-specific — supported by >= 2 but < 50% of documents, using EXACT MECHANISM NAMES>"
    ],
    "variant_dont": [
      "<anti-pattern that is valid but content-type-specific, using EXACT MECHANISM NAMES>"
    ]
  }}
}}

STRUCTURAL DNA PROFILES TO CONSOLIDATE:
{structural_profiles}"""


# ---------------------------------------------------------------------------
# PASS 4 — BEST EXAMPLE SELECTION (UNCHANGED)
# ---------------------------------------------------------------------------

PASS4_BEST_EXAMPLE_SELECTION = """You are a writing pattern evaluator. You have been given {total_documents} document opening and closing ABSTRACTIONS produced by Pass 2.5.

Your job is to score each abstraction and select the best ones. Because you are scoring pre-abstracted structural representations (not raw text), your focus is on:

- Structural robustness: Does the skeleton hold up across topics?
- Move clarity: Are the rhetorical functions clearly defined?
- Replicability: Can a writer follow this for any topic?
- Canonical alignment: Does it match the brand's canonical patterns from Pass 3?

SCORING RUBRIC (0-10):
- Structure clarity: 3+ distinct moves with clear functions? (0-3)
- Evidence accommodation: Does the structure have slots for concrete anchoring? (0-2)
- Distinctiveness: Could this structure belong to any brand? (0-3)
- Replicability: Can it be applied to a completely different topic? (0-2)

RULES:
1. Score every opening abstraction and every closing abstraction independently.
2. Select the single highest-scoring opening and highest-scoring closing.
3. The selected skeletons are already abstract from Pass 2.5 — include them verbatim.
4. If two abstractions score equally, prefer the one with higher topic_independence_score from Pass 2.5.
5. Never copy phrases or sentences from the source documents. You are working with abstractions, so this should be impossible.

SKELETON QUALITY RULES — these are MANDATORY:
A skeleton that uses only generic placeholders like [CLAIM], [EXPLANATION], [EVIDENCE] is NOT acceptable.
A good skeleton must:
- Describe the RHETORICAL FUNCTION of each sentence in parentheses
- Specify APPROXIMATE LENGTH for each sentence
- Describe the TRANSITION MECHANISM between sentences
- Make generic substitution structurally impossible

BAD skeleton example (too generic — reject this):
  "[CLAIM]. [EXPLANATION]. [EVIDENCE]."

GOOD skeleton example (specific enough to prevent clichés):
  "[UNCOMFORTABLE TRUTH about what most [TARGET AUDIENCE] get wrong about [TOPIC] —
  stated as present-tense observation, no hedging, 8-12 words].
  [PIVOT using brand's direct experience — 'At [BRAND NAME], we've seen this in
  [SPECIFIC NUMBER] [CLIENT TYPE]' — 15-20 words].
  [REFRAME: split what [TARGET AUDIENCE] think [TOPIC] is from what it actually is
  in the brand's framework — two parallel clauses, 20-25 words total]."

Apply this same standard to the closing skeleton.

Return ONLY a JSON object. No preamble, markdown, or explanation.

{{
  "brand_name": "<brand name extracted from documents>",
  "content_type": "<content type these documents share>",
  "total_documents_evaluated": {total_documents},

  "opening_scores": [
    {{
      "document_index": <integer>,
      "score": <0-10>,
      "score_breakdown": {{
        "structure_clarity": <0-3>,
        "evidence_accommodation": <0-2>,
        "distinctiveness": <0-3>,
        "replicability": <0-2>
      }},
      "topic_independence_score": <from Pass 2.5>,
      "why": "<one sentence explaining why this scored as it did, referencing structural moves>"
    }}
  ],

  "closing_scores": [
    {{
      "document_index": <integer>,
      "score": <0-10>,
      "score_breakdown": {{
        "structure_clarity": <0-3>,
        "evidence_accommodation": <0-2>,
        "distinctiveness": <0-3>,
        "replicability": <0-2>
      }},
      "topic_independence_score": <from Pass 2.5>,
      "why": "<one sentence explaining why this scored as it did, referencing structural moves>"
    }}
  ],

  "best_opening": {{
    "source_document_index": <integer>,
    "score": <0-10>,
    "move_sequence": [
      "<Move 1: describe what this move does — the rhetorical function, with parenthetical note on sentence length>",
      "<Move 2: describe what this move does>",
      "<Move 3: describe what this move does>",
      "<Move 4 if present>"
    ],
    "skeleton": "<include the Pass 2.5 skeleton verbatim — it is already abstract and topic-independent>",
    "execution_notes": "<any important nuances a writer needs to know to execute this correctly. Reference canonical patterns where relevant.>"
  }},

  "best_closing": {{
    "source_document_index": <integer>,
    "score": <0-10>,
    "move_sequence": [
      "<Move 1: describe what this move does>",
      "<Move 2: describe what this move does>",
      "<Move 3: describe what this move does>"
    ],
    "skeleton": "<include the Pass 2.5 skeleton verbatim>",
    "execution_notes": "<any important nuances a writer needs to know to execute this correctly.>"
  }},

  "runner_up_opening": {{
    "source_document_index": <integer>,
    "score": <0-10>,
    "skeleton": "<reconstructed skeleton>",
    "when_to_use": "<describe what content type or tone this opening suits better than the best one>"
  }},

  "runner_up_closing": {{
    "source_document_index": <integer>,
    "score": <0-10>,
    "skeleton": "<reconstructed skeleton>",
    "when_to_use": "<describe what content type or tone this closing suits better than the best one>"
  }}
}}

CANONICAL PATTERNS FROM PASS 3 (use as reference standard):
{canonical_patterns}

DOCUMENT ABSTRACTIONS TO EVALUATE (from Pass 2.5 — no verbatim text):
{documents_with_abstractions}"""


# ---------------------------------------------------------------------------
# UPDATED METRICS_SYNTHESIS
# ---------------------------------------------------------------------------

METRICS_SYNTHESIS = """You are a brand intelligence analyst. You have been given extracted writing intelligence from {total_documents} documents belonging to the same brand, processed through five extraction passes:

- DOCUMENT INVENTORY (Pass 0): verbatim openings/closings and structural classifications
- BRAND ASSET BANKS (Pass 2): specific facts, numbers, named frameworks, stated values
- CROSS-DOCUMENT PATTERN CONSOLIDATION (Pass 3): canonical, near-canonical, and variant patterns
- BEST EXAMPLE SELECTION (Pass 4): scored and reconstructed opening and closing skeletons from Pass 2.5 abstractions

Your job is to synthesize all five into a single brand writing intelligence brief that a content writer can use to produce original content that is structurally and tonally indistinguishable from this brand's voice — on ANY topic.

SYNTHESIS RULES:
- Pass 3 canonical and near-canonical patterns are the highest-confidence outputs. State them confidently.
- Pass 3 variant patterns are valid but content-type-specific. Include them with clear context.
- Pass 4 opening and closing skeletons are the highest-priority structural outputs — include them verbatim. They are already abstract and topic-independent from Pass 2.5.
- ASSET BANK facts must be preserved exactly — never paraphrase numbers or named frameworks.
- Generation instructions must be entirely pattern-based — no content references, only structural and tonal mechanics.
- Do not invent patterns not present in the source profiles. State "Insufficient data" where needed.
- If a pattern was not detected as canonical or near-canonical (e.g., the brand uses different openings for different content types), say so explicitly rather than forcing a single canonical pattern.
- Use EXACT MECHANISM NAMES from Pass 3 in all descriptions. Do not water down canonical patterns to generic language.
- Include NEAR-CANONICAL patterns in the brief with a note that they need more data to confirm.

Business: {business_id}
Content type: {content_type}

DOCUMENT INVENTORY (Pass 0):
{document_inventory}

BRAND ASSET BANKS (Pass 2):
{asset_banks}

CROSS-DOCUMENT PATTERN CONSOLIDATION (Pass 3):
{pattern_consolidation}

BEST EXAMPLE SELECTION (Pass 4):
{example_selection}

Return your synthesis as a well-structured plain text brand writing intelligence brief. Use clear section headers starting with #.

Structure your output exactly as follows:

# BRAND NAME
[Brand name. If not found: Not extracted — inject manually.]

# BRAND VOICE OVERVIEW
[2-3 sentences on HOW this brand writes — register, authority style, reader relationship, intellectual stance. No content references.]

# In METRICS_SYNTHESIS:
BRAND ASSET BANK CONSOLIDATION RULES:
1. Merge ALL social proof assets from ALL documents. Deduplicate by claim text.
2. Preserve ALL named frameworks from ALL documents. Do not filter — if a framework
   appears in any document, include it.
3. Collect ALL domain vocabulary from ALL documents. Deduplicate and sort alphabetically.
4. Collect ALL stated values from ALL documents.
5. If an asset appears in multiple documents with different numbers, include the
   most specific version (the one with exact numbers).
6. Flag assets that appear in only 1 document as "needs confirmation" rather than
   omitting them.

# CANONICAL STRUCTURAL FORMULA
[If a canonical or near-canonical formula was detected in Pass 3, describe it here as the primary architecture the brand uses across content types.]
[Move sequence using EXACT MECHANISM NAMES:]
1. [Move 1 description — e.g. "pattern-interrupting uncomfortable truth stated as present-tense observation"]
2. [Move 2 description — e.g. "authority-establishing social proof anchor with exact client count and outcome percentage"]
3. [Move 3 description — e.g. "tripartite negation-reframe using [X] isn't [Y]. It isn't [Z]. It's [W]."]
...

[Canonical skeleton — verbatim from Pass 3 canonical_formula.canonical_skeleton:]
---
[SKELETON HERE]
---

[If NO canonical or near-canonical formula was detected, state: "No single canonical formula detected across documents. The brand uses variant structures depending on content type."]

# INTELLECTUAL PATTERNS

DIAGNOSTIC STYLE:
[Description from Pass 3 using EXACT MECHANISM NAMES + canonical skeleton]

REFRAMING MOVE:
[Description from Pass 3 using EXACT MECHANISM NAMES + canonical skeleton]

ARGUMENT STRUCTURE:
[Canonical sequence from Pass 3 using EXACT MECHANISM NAMES]

THINKING TEMPLATES:
[ALL canonical and near-canonical sentence-level moves with skeletons from Pass 3 thinking_templates_consolidated:]
- Move 1: [description using EXACT MECHANISM NAMES] | Skeleton: [frame]
- Move 2: [description using EXACT MECHANISM NAMES] | Skeleton: [frame]
- Move 3: [description using EXACT MECHANISM NAMES] | Skeleton: [frame]
[Include near-canonical templates with a note.]

# STYLE SIGNATURE

MECHANICAL RULES:
- Sentence rhythm: [pattern description using EXACT MECHANISM NAMES with length-to-function mapping + canonical skeleton from Pass 3]
- Paragraph constraints: [opening / body / closing patterns from Pass 3]
- Evidence anchoring rule: [the rule using EXACT MECHANISM NAMES + canonical skeleton from Pass 3]
- Heading format: [convention if detected, else "Not specified"]

# TONE SIGNATURE
[Register, assertiveness, hedging rules, reader relationship — from Pass 3 tone_consolidation. Be specific.]

# STRUCTURE SIGNATURE

OPENING PATTERN:
[If canonical or near-canonical: Move sequence from Pass 3 using EXACT MECHANISM NAMES + canonical skeleton from Pass 4 best_opening.]
[If variant: Note which content types use which opening pattern, and include the best skeleton for the primary content type.]

[Canonical skeleton — verbatim from Pass 4 best_opening.skeleton:]
---
[SKELETON HERE]
---

Execution notes: [from Pass 4]

CLOSING PATTERN:
[If canonical or near-canonical: Move sequence from Pass 3 using EXACT MECHANISM NAMES + canonical skeleton from Pass 4 best_closing.]
[If variant: Note which content types use which closing pattern.]

[Canonical skeleton — verbatim from Pass 4 best_closing.skeleton:]
---
[SKELETON HERE]
---

Execution notes: [from Pass 4]

SECTION PATTERN:
[How body sections are structured — from Pass 3 canonical patterns using EXACT MECHANISM NAMES.]

NARRATIVE ARC:
[Standard flow as a sequence of functional moves using EXACT MECHANISM NAMES — from Pass 3 narrative_arc.]

# SIGNATURE CONSTRUCTIONS
[ALL canonical and near-canonical distinctive constructions from Pass 3 signature_constructions_consolidated:]
- Construction 1: [what it does using EXACT MECHANISM NAMES, confidence level] | Skeleton: [frame]
- Construction 2: [what it does using EXACT MECHANISM NAMES, confidence level] | Skeleton: [frame]
[Include near-canonical constructions with a note that they need more data.]

# GENERATION INSTRUCTIONS

DO (CANONICAL — apply to all content types):
- [Pattern-based instruction using EXACT MECHANISM NAMES from Pass 3 consolidated do list. minimum 8.]

DON'T (CANONICAL — avoid in all content types):
- [Anti-pattern instruction using EXACT MECHANISM NAMES from Pass 3 consolidated dont list. minimum 5.]

DO (NEAR-CANONICAL — apply with caution, may need more data):
- [Pattern-based instruction from Pass 3 near-canonical do list.]

DON'T (NEAR-CANONICAL — avoid with caution):
- [Anti-pattern instruction from Pass 3 near-canonical dont list.]

DO (VARIANT — apply when content type matches):
- [Content-type-specific instruction using EXACT MECHANISM NAMES from Pass 3 variant_do list.]

DON'T (VARIANT — avoid when content type matches):
- [Content-type-specific anti-pattern using EXACT MECHANISM NAMES from Pass 3 variant_dont list.]

CONFIDENCE ASSESSMENT RULES:
1. State which dimensions are canonical (>=60% of documents support them)
2. State which dimensions are near-canonical (>=50% support)
3. State which dimensions have insufficient data (<50% support or missing)
4. Be honest about gaps in the asset bank, vocabulary, or values
5. Do not claim "well-established" if the section is clearly incomplete """