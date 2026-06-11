from typing import TypedDict, Optional, List


class GraphState(TypedDict):
    # Input
    business_id: str
    content_type: str
    topic: str
    format_type: str
    user_id: Optional[int]
    use_search: bool

    webhook_url: Optional[str]
    human_feedback: Optional[str]

    # Researcher output
    research: str

    # Brand context — fetched once by writer_node, passed through all nodes
    brand_context: Optional[dict]
    approved_angles: Optional[str]
    rejected_angles: Optional[str]

    # Writer output
    content: str
    creative_angle: str
    iteration: int

    # Enforcer output
    approved: bool
    score: float
    feedback: str
    style_match: float
    tone_match: float
    structure_match: float
    signature_match: float

    # Fabrication detection — set by enforcer, consumed by writer revision
    fabrication_detected: bool
    fabricated_claims: Optional[List[str]]

    # Final output
    generation_id: str
    status: str