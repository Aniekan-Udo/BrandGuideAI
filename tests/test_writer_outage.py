"""A writer whose model fails never puts the error into the post.

Observed in a live run on Gemini's free tier: the writer hit a 429, wrote
"[System Error: Unable to revise content - Error code: 429 ...]" into the
draft, and the deployer published that line as the finished blog post.
"""
import httpx
import pytest

import graph.deps
import nodes.writer as writer
from nodes.deployer import deployer_node
from nodes.enforcer import enforcer_node
from utils.provider_errors import retry_after


def _http_error(status, message):
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    return httpx.HTTPStatusError(f"Error code: {status} - {message}", request=request,
                                 response=httpx.Response(status, request=request))


PER_MINUTE = _http_error(429, "You exceeded your current quota. Please retry in 46.9s.")
PER_DAY = _http_error(429, "Quota exceeded. 'retryDelay': '69904s'")
OVERLOADED = _http_error(503, "This model is currently experiencing high demand.")


class _Reply:
    def __init__(self, content):
        self.content = content


class _Model:
    """Answers or raises, one scripted outcome per call."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def invoke(self, _prompt):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _Reply(outcome)


class _Deps:
    def get_context(self):
        return "# BRAND VOICE PROFILE\nShort, plain sentences.\n"

    def query_structure(self, *_a, **_k):
        return []

    def get_patterns(self, *_a, **_k):
        return {"approved": [], "rejected": []}

    def save(self, *_a, **_k):
        return None


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(graph.deps, "resolve_deps", lambda *_a: (_Deps(), _Deps(), _Deps()))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    def use(*outcomes):
        fake = _Model(*outcomes)
        monkeypatch.setattr("model.LLMSingleton.get", lambda *a, **k: fake)
        return fake

    return use


def _state(**extra):
    state = {"business_id": "b1", "content_type": "blog", "topic": "Refill stations",
             "format_type": "blog", "research": "Refills cost £2.80 per 500 ml bottle.",
             "iteration": 0, "feedback": "", "violation_history": []}
    state.update(extra)
    return state


class TestHowLongToWait:
    def test_a_per_minute_limit_says_when(self):
        assert retry_after(PER_MINUTE) == pytest.approx(46.9)

    def test_a_daily_quota_reports_its_real_wait(self):
        assert retry_after(PER_DAY) == 69904

    def test_an_overloaded_model_gets_a_short_wait(self):
        assert retry_after(OVERLOADED) == 10.0

    def test_a_bad_request_is_not_retried(self):
        assert retry_after(_http_error(400, "Invalid argument")) is None


class TestTheFirstRound:
    def test_a_busy_provider_is_retried_once(self, model):
        fake = model(PER_MINUTE, "outline", "draft", "final")
        assert writer.writer_node(_state())["content"] == "final"
        assert fake.calls == 4

    def test_a_daily_quota_is_not_waited_out(self, model):
        fake = model(PER_DAY, "draft", "final")
        assert writer.writer_node(_state())["content"] == "final"
        assert fake.calls == 3, "the planner gave up at once and the piece was drafted without it"

    def test_no_draft_fails_the_generation_instead_of_publishing_the_error(self, model):
        model("outline", PER_DAY)
        with pytest.raises(writer.WriterUnavailable):
            writer.writer_node(_state())

    def test_a_failed_edit_passes_on_the_real_draft(self, model):
        model("outline", "the unedited draft", PER_DAY)
        assert writer.writer_node(_state())["content"] == "the unedited draft"

    def test_a_bug_in_our_code_still_raises(self, model):
        model(KeyError("format"))
        with pytest.raises(KeyError):
            writer.writer_node(_state())


class TestARevisionRound:
    JUDGED = "The draft the enforcer already scored."

    def _revise(self, model, *outcomes):
        model(*outcomes)
        return writer.writer_node(_state(iteration=2, content=self.JUDGED, score=6.0,
                                         feedback="Tighten the opening."))

    def test_a_failed_revision_keeps_the_judged_draft(self, model):
        state = self._revise(model, PER_DAY)
        assert state["content"] == self.JUDGED
        assert "HTTPStatusError" in state["writer_unavailable"]

    def test_the_enforcer_ends_the_loop_without_judging_again(self, model, monkeypatch):
        state = self._revise(model, PER_DAY)
        monkeypatch.setattr("model.LLMSingleton.get",
                            lambda *a, **k: pytest.fail("the judge was called"))
        judged = enforcer_node(state)
        assert judged["approved"] is False
        assert judged["iteration"] >= 3
        assert judged["feedback"].startswith("WRITER UNAVAILABLE")
        assert judged["content"] == self.JUDGED

    def test_the_best_round_is_what_gets_delivered(self, model, monkeypatch):
        state = self._revise(model, PER_DAY)
        state = enforcer_node({**state, "best_content": "The 7.5 round.", "best_score": 7.5,
                               "best_iteration": 1, "generation_id": "g1"})

        class _NoDb:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, *a, **k):
                return None

            def commit(self):
                return None

        monkeypatch.setattr("nodes.deployer.get_db_session", lambda: _NoDb())
        delivered = deployer_node(state)
        assert delivered["content"] == "The 7.5 round."
