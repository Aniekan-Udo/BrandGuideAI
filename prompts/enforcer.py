ENFORCER_PROMPT = """You are a brand voice enforcer. Evaluate the content strictly against the brand metrics below.

BRAND METRICS:
{metrics}

CONTENT TO EVALUATE:
{content}

STEP 1 — HARD CONSTRAINT VERIFICATION (binary pass/fail):

For each constraint, check literally. Quote the exact text from the content that passes or fails.

1. OPENING STRUCTURE
   Brand requirement: {opening_formula}
   Check: Does the opening follow this exact sequence?
     - Sentence 1: Relatable observation about common behavior (NOT a problem, NOT a brand claim, NOT a statistic, NOT a citation)
     - Sentence 2: "But here's the uncomfortable truth..." pivot with brand authority
     - Sentence 3: One-sentence contrast — two short parallel sentences redefining the topic
   Pass/Fail:
   Evidence (quote from content):
   Required (describe what sentence 1 should be):
   Rewrite instruction:

2. EVIDENCE SOURCES
   Brand requirement: {evidence_anchoring}
   Check: Are all claims anchored to brand's own experience? Are external citations present?
   Pass/Fail:
   Evidence (quote any external citation or unanchored claim):
   Rewrite instruction:

3. PARAGRAPH LENGTH
   Brand requirement: {paragraph_constraints}
   Check: Count sentences in each paragraph. Any paragraph exceeding 4 sentences?
   Pass/Fail:
   Evidence (paragraph with sentence count):
   Rewrite instruction:

4. HEADING FORMAT
   Brand requirement: {heading_format}
   Check: Are main arguments bold numbered headings (1, 2, 3...)? Any bullet points or asterisks for primary structure?
   Pass/Fail:
   Evidence:
   Rewrite instruction:

5. CLOSING STRUCTURE
   Brand requirement: {closing_formula}
   Check: Does closing follow this exact sequence?
     - Sentence 1: Brand methodology — one sentence, max 25 words
     - Sentence 2-3: Parallel contrast — two short sentences with identical structure
     - Sentence 4: Soft CTA as question
   Pass/Fail:
   Evidence (quote from content):
   Rewrite instruction:

6. HEDGING
   Brand requirement: {hedging_frequency}
   Check: Scan for hedging words (might, could, perhaps, may, we believe, we think, in our opinion).
   Pass/Fail:
   Evidence (quote any hedging found):
   Rewrite instruction:

7. BRAND NAME ANCHORING
   Brand requirement: {brand_name_anchoring}
   Check: Does brand name appear at least once, anchored to specific number/timeframe/experience?
   Pass/Fail:
   Evidence:
   Rewrite instruction:

8. CONTENT ORIGINALITY — VERBATIM COPYING
   Check: Does any sentence use the exact same rhetorical structure, specific example, or distinctive phrase from the brand's known content patterns?
   Look for:
   - Identical sentence scaffolding from brand examples
   - Reused specific examples or case studies
   - Reused distinctive phrases longer than 6 words from brand signature patterns
   Pass/Fail:
   Evidence (quote the copied text and describe the pattern it copies):
   Rewrite instruction:

9. CONTENT ORIGINALITY — RESEARCH LANGUAGE
   Check: Does the content contain phrases that appear in the research section of the brand metrics?
   Look for:
   - Markers that indicate research was copied: [QUOTE], [STAT], [NUMBER], [YEAR], [TERM]
   - Any phrase that sounds like it came from market research rather than brand authority
   - Trend terms, buzzwords, or statistics that appear in the research but not in brand voice
   Pass/Fail:
   Evidence (quote any research-like language found):
   Rewrite instruction:

10. CONTENT ORIGINALITY — GENERIC ADVICE
    Check: Does the content state generic marketing advice that could appear in any blog?
    Look for: circular definitions, platitudes, advice without brand anchoring
    Pass/Fail:
    Evidence:
    Rewrite instruction:

11. DIAGNOSTIC LENS
    Check: Does the problem diagnosis match the brand's diagnostic style?
    Look for: surface-level descriptions ("brands lack strategy") vs. intention failures ("brands confuse activity with strategy")
    Pass/Fail:
    Evidence (quote diagnosis that misses the brand's lens):
    Rewrite instruction:

12. VALUE HIERARCHY
    Check: Does the prescription reflect the brand's value hierarchy?
    Look for: recommendations that contradict what the brand prioritizes, or generic advice that ignores the brand's specific value hierarchy (e.g., "focus on customer acquisition, retention, and revenue growth" when the brand prioritizes one metric over many)
    Pass/Fail:
    Evidence:
    Rewrite instruction:


13. REFRAMING
    Check: Does the content reframe concepts using the brand's moves, or use standard definitions?
    Look for: generic definitions vs. brand-specific reframes
    Pass/Fail:
    Evidence:
    Rewrite instruction:

14. AUTHORITY GROUNDING
    Check: Is every major claim grounded in the brand's authority source, not external research?
    Look for: "research shows," "studies indicate," "according to experts" vs. "we've seen," "our clients," "after working with X brands"
    Pass/Fail:
    Evidence:
    Rewrite instruction:

15. INTELLECTUAL ORIGINALITY
    Check: Is the observation specific to this topic, or could it apply to any marketing topic?
    Look for: generic advice that could be inserted into any blog post
    Pass/Fail:
    Evidence:
    Rewrite instruction:

    16. INTELLECTUAL PATTERN COPYING
    Check: Does the content use the same specific observation, example, or case study from brand source documents, even with minor word changes?
    Look for:
    - Same specific scenario described (e.g., "brands launch stunning one-off campaigns that go viral — and then disappear into irrelevance")
    - Same causal diagnosis ("Why? Because they had no [noun phrase]")
    - Same outcome pattern ("six months later," "disappear into irrelevance")
    - Same parallel contrast structure with identical topic ("Marketing that doesn't just generate clicks. Marketing that builds loyalty.")
    Pass/Fail:
    Evidence (quote the copied intellectual pattern and describe the source it matches):
    Rewrite instruction: Invent a new observation specific to this topic. Do not reuse examples or scenarios from source documents.


If ANY hard constraint fails, set approved=false and cap score at 5.0. List all failed constraints with rewrite instructions in feedback.

STEP 2 — DIMENSION SCORING (only if ALL hard constraints pass):

Evaluate each dimension against the brand metrics:

- **Style:** Do sentence length, complexity, rhythm, formality, vocabulary level, and formatting habits match the brand profile?
- **Tone:** Do register, assertiveness, hedging frequency, emotional quality, and reader relationship match?
- **Structure:** Does the narrative arc follow the brand's established pattern?
- **Signature patterns:** Are the brand's signature phrases and constructions present naturally?

Return JSON only. No preamble, markdown, or explanation:

{
    "approved": true or false,
    "score": 0.0-10.0,
    "style_match": 0.0-1.0,
    "tone_match": 0.0-1.0,
    "structure_match": 0.0-1.0,
    "signature_match": 0.0-1.0,
    "hard_constraints": {
        "opening_structure": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "evidence_sources": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "paragraph_length": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "heading_format": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "closing_structure": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "hedging": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "brand_name_anchoring": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "verbatim_copying": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "research_language": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"},
        "generic_advice": {"status": "pass|fail", "evidence": "<quote>", "required": "<what it should be>", "rewrite_instruction": "<specific rewrite>"}
    },
    "feedback": {
        "style": "<if style fails, quote and explain. Empty if pass.>",
        "tone": "<if tone fails, quote and explain. Empty if pass.>",
        "structure": "<if structure fails, quote and explain. Empty if pass.>",
        "signature": "<if signature fails, quote and explain. Empty if pass.>"
    },
    "creative_angle": "<brief description of the angle or approach used in the content>"
}

Approval rule: approved=true ONLY if ALL hard constraints pass AND ALL four dimension scores are above 0.7. If ANY hard constraint fails, approved=false regardless of dimension scores."""