from typing import TypedDict, Optional, Dict, Any

class GraphState(TypedDict):
    # Input
    business_id: str
    content_type: str
    topic: str
    format_type: str
    user_id: Optional[int]
    use_search: bool

    # Researcher output
    research: str

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
    hard_constraint_evidence: Optional[Dict[str, Any]]  

    # Final output
    generation_id: str
    status: str
