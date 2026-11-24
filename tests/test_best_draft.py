"""An unapproved run delivers its best round, not its last one.

Observed, in a run that ended "Needs review" with the rounds exhausted:

    6.3 -> 6.3 -> 7.5 -> 7.5 -> 6.0 -> [story gate] -> [facts gate]

The 7.5 existed and was thrown away. What was delivered came from a later,
worse round, and that draft had also turned "more than seven men" into "Seven
men sat together". Revision is not monotonic: each round rewrites the whole
piece from feedback, and a round that fixes one fault can break something the
round before had right.
"""
import pytest

import graph.deps
from nodes.deployer import deployer_node
from nodes.enforcer import enforcer_node

BRAIN = """# BRAND VOICE PROFILE
Short, plain sentences.

# PUNCTUATION HABITS
- Em dashes: never

# MEASURED MECHANICS
- exclamation_marks_per_100_words: 0.0
- median_words_per_sentence: 7.0
- bracket_placeholders_per_100_words: 0.0
- nominalisations_per_100_words: 1.2
- nominalisations_per_100_words_low: 0.8
- nominalisations_per_100_words_high: 3.1

# STRUCTURAL PATTERNS
Opens on a scene.
"""

SOURCE = ("After lectures he calls the number. He finds a group of more than seven men, seated, "
          "drinking. They tell him to drink with them. He says no.")

GOOD = "He calls after lectures.\n\nMore than seven men. Seated. Drinking.\n\nHe says no."
LATER = "He calls after lectures.\n\nMore than seven men sit and drink.\n\nHe says no. The mood turns."


class _Analyzer:
    def get_context(self):
        return BRAIN


class _Scored:
    def __init__(self, score, **overrides):
        self.payload = {
            "hallucination_check": {"verdict": "PASS", "hallucinated_claims": []},
            "structural_precheck": {"opening_pattern": True, "closing_pattern": True,
                                    "signature_constructions": {}, "evidence_anchoring": True,
                                    "sentence_rhythm": True, "hedging_violations": []},
            "voice_score": 9.0, "voice_rewrites": [], "voice_subject": "",
            "approved": False, "directive_compliance": "NOT_APPLICABLE",
            "publishability": "PASS", "score": score,
            "style_match": 0.8, "tone_match": 0.8, "structure_match": 0.8, "signature_match": 0.8,
            "feedback": "keep going", "flagged_passages": [], "creative_angle": "a retelling",
        }
        self.payload.update(overrides)

    def invoke(self, _prompt):
        import json
        from types import SimpleNamespace
        return SimpleNamespace(content=json.dumps(self.payload))


@pytest.fixture
def score_round(monkeypatch):
    """Run one enforcer round at a given score, carrying state forward."""
    def run(content, score, state=None, **overrides):
        monkeypatch.setattr(
            graph.deps, "resolve_deps",
            lambda business_id, content_type: (None, _Analyzer(), None),
        )
        monkeypatch.setattr("model.LLMSingleton.get", lambda *a, **k: _Scored(score, **overrides))
        base = {
            "business_id": "b1", "content_type": "script", "topic": "t",
            "research": SOURCE, "content": content, "iteration": 1,
            "violation_history": [],
        }
        base.update(state or {})
        base["content"] = content
        return enforcer_node(base)

    return run


class TestTheBestRoundIsRemembered:
    def test_a_better_round_replaces_the_earlier_best(self, score_round):
        state = score_round(GOOD, 6.3)
        assert state["best_score"] == 6.3
        state = score_round(LATER, 7.5, state)
        assert state["best_score"] == 7.5 and state["best_content"] == LATER

    def test_a_worse_round_does_not(self, score_round):
        """The failure this exists for: 7.5 then 6.0, and the 6.0 shipped."""
        state = score_round(LATER, 7.5)
        state = score_round(GOOD, 6.0, state)
        assert state["best_score"] == 7.5 and state["best_content"] == LATER

    def test_a_clean_round_beats_a_higher_scoring_dirty_one(self, score_round):
        """A score cannot see a lost fact. The deterministic gates can, so a
        draft that cleared them is preferred to one that merely scored well."""
        state = score_round(GOOD, 6.0)
        state = score_round(LATER, 9.0, state, publishability="FAIL — internal material")
        assert state["best_content"] == GOOD, "a draft that failed a gate became the best"

    def test_the_round_it_came_from_is_recorded(self, score_round):
        state = score_round(GOOD, 6.3, {"iteration": 3})
        assert state["best_iteration"] == 3


class TestWhatIsDelivered:
    def _deploy(self, monkeypatch, state):
        saved = {}

        class _Memory:
            def save(self, **kwargs):
                saved.update(kwargs)

        monkeypatch.setattr(
            graph.deps, "resolve_deps",
            lambda business_id, content_type: (None, _Analyzer(), _Memory()),
        )
        monkeypatch.setattr("nodes.deployer.get_db_session", lambda: _NoDb())
        return deployer_node(state), saved

    def test_an_unapproved_run_hands_over_its_best_draft(self, monkeypatch):
        state = {
            "generation_id": "g1", "business_id": "b1", "content_type": "script",
            "topic": "t", "format_type": "f", "approved": False,
            "content": GOOD, "score": 6.0,
            "best_content": LATER, "best_score": 7.5, "best_iteration": 3,
        }
        result, saved = self._deploy(monkeypatch, state)
        assert result["content"] == LATER and result["score"] == 7.5
        assert saved["generated_content"] == LATER, "memory must learn from what shipped"

    def test_an_approved_draft_is_never_substituted(self, monkeypatch):
        """The approval belongs to the draft that earned it."""
        state = {
            "generation_id": "g1", "business_id": "b1", "content_type": "script",
            "topic": "t", "format_type": "f", "approved": True,
            "content": GOOD, "score": 8.2,
            "best_content": LATER, "best_score": 9.0, "best_iteration": 2,
        }
        result, _ = self._deploy(monkeypatch, state)
        assert result["content"] == GOOD

    def test_a_run_with_nothing_better_is_left_alone(self, monkeypatch):
        state = {
            "generation_id": "g1", "business_id": "b1", "content_type": "script",
            "topic": "t", "format_type": "f", "approved": False,
            "content": GOOD, "score": 7.5,
            "best_content": GOOD, "best_score": 7.5, "best_iteration": 1,
        }
        result, _ = self._deploy(monkeypatch, state)
        assert result["content"] == GOOD and result["score"] == 7.5

    def test_a_run_that_recorded_no_best_still_deploys(self, monkeypatch):
        """Every early return from the enforcer skips the scoring call, so a run
        refused on its first round has no best draft to fall back to."""
        state = {
            "generation_id": "g1", "business_id": "b1", "content_type": "script",
            "topic": "t", "format_type": "f", "approved": False,
            "content": GOOD, "score": 0.0,
        }
        result, _ = self._deploy(monkeypatch, state)
        assert result["content"] == GOOD


class _NoDb:
    """Stands in for a database session; the deployer's writes are not under test."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a, **k):
        return None

    def commit(self):
        return None


class _Unreachable:
    """A judge whose provider refuses the request, as Groq's free tier did with
    a 413 when the third round's prompt exceeded its tokens-per-minute limit."""

    def invoke(self, _prompt):
        import httpx
        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        response = httpx.Response(413, request=request)
        raise httpx.HTTPStatusError(
            "Error code: 413 - Request too large for model on tokens per minute",
            request=request, response=response,
        )


LOST_FACT = "He calls after lectures.\n\nSeven men sit and drink.\n\nHe says no."


@pytest.fixture
def judge_down(monkeypatch):
    def run(content, state=None):
        monkeypatch.setattr(
            graph.deps, "resolve_deps",
            lambda business_id, content_type: (None, _Analyzer(), None),
        )
        monkeypatch.setattr("model.LLMSingleton.get", lambda *a, **k: _Unreachable())
        base = {
            "business_id": "b1", "content_type": "script", "topic": "t",
            "research": SOURCE, "content": content, "iteration": 3,
            "violation_history": [],
        }
        base.update(state or {})
        base["content"] = content
        return enforcer_node(base)

    return run


class TestWhenTheJudgeCannotBeReached:
    """A provider outage ends the run with a draft; it never fails the generation."""

    def test_the_run_ends_instead_of_raising(self, judge_down):
        from utils.enforcement.constants import MAX_ITERATIONS
        state = judge_down(GOOD, {"iteration": 1})
        assert state["iteration"] == MAX_ITERATIONS, "must route to the deployer, not loop"
        assert state["approved"] is False, "an unjudged draft is never approved"
        assert state["feedback"].startswith("JUDGE UNAVAILABLE")
        assert "413" in state["feedback"], "say why, so the operator can act on it"

    def test_a_draft_that_passed_every_code_check_is_delivered(self, judge_down):
        state = judge_down(GOOD, {"best_content": LATER, "best_score": 6.0, "best_iteration": 2})
        assert state["content"] == GOOD
        assert state["best_content"] == GOOD, "the deployer must not swap it back"
        assert "passed every code check" in state["feedback"]

    def test_a_draft_still_failing_a_code_check_gives_way_to_the_best_judged_round(self, judge_down):
        history = ["state the source's facts exactly: more than seven men"] * 2
        state = judge_down(LOST_FACT, {
            "violation_history": history,
            "best_content": GOOD, "best_score": 6.5, "best_iteration": 2, "best_was_clean": True,
        })
        assert state["content"] == GOOD and state["score"] == 6.5
        assert "round 2" in state["feedback"]

    def test_with_nothing_judged_before_the_failing_draft_is_delivered_and_says_so(self, judge_down):
        history = ["state the source's facts exactly: more than seven men"] * 2
        state = judge_down(LOST_FACT, {"violation_history": history})
        assert state["content"] == LOST_FACT
        assert "still fails these code checks" in state["feedback"]
        assert state["best_was_clean"] is False

    def test_the_deployer_hands_over_what_the_enforcer_chose(self, judge_down, monkeypatch):
        state = judge_down(GOOD, {"best_content": LATER, "best_score": 6.0, "best_iteration": 2})
        state.update({"generation_id": "g1", "format_type": "f"})
        result, _ = TestWhatIsDelivered()._deploy(monkeypatch, state)
        assert result["content"] == GOOD

    def test_a_bug_in_our_own_code_is_not_reported_as_an_outage(self, monkeypatch):
        class _Broken:
            def invoke(self, _prompt):
                raise KeyError("a bug, not an outage")

        monkeypatch.setattr(graph.deps, "resolve_deps",
                            lambda business_id, content_type: (None, _Analyzer(), None))
        monkeypatch.setattr("model.LLMSingleton.get", lambda *a, **k: _Broken())
        with pytest.raises(KeyError):
            enforcer_node({"business_id": "b1", "content_type": "script", "topic": "t",
                           "research": SOURCE, "content": GOOD, "iteration": 1,
                           "violation_history": []})
