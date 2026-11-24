"""The phrases a brand repeats word for word, and the spelling it writes in.

Observed in a live run: three posts that each ended "Rinse. Refill. Repeat."
and each used "Here's the thing." produced a Brain that recorded neither, and a
draft that ended "Bring. Fill. Tap. Go." and spelled "colorful", "realize" and
"math" for a British brand.
"""
from utils.brand_fixtures import (
    ends_with_sign_off,
    measure_fixtures,
    render_fixtures,
    respell,
    sign_off_from,
    spelling_from,
    spelling_variety,
)
from utils.enforcement.preflight import run_preflight_checks
from utils.voice_spec import corpus_spec, render_spec

POSTS = [
    "The Cupboard Is Lying\n\nOpen the cupboard. Count the bottles.\n\nHere's the thing. "
    "Every bottle is mostly water.\n\nBright colours, bold claims.\n\nRinse. Refill. Repeat.",
    "Nobody Enjoys Bathrooms\n\nLet's not pretend.\n\nHere's the thing. Most cleaners are built "
    "to impress you in the shop.\n\nSpray. Wait. Wipe.\n\nRinse. Refill. Repeat.",
    "We Counted the Bottles\n\nWe asked 50 customers to keep their bottles.\n\nHere’s the "
    "thing. Nobody knows how much comes from the sink.\n\nFig leaf is the favourite scent.\n\n"
    "Rinse. Refill. Repeat.",
]


class TestWhatIsMeasured:
    def test_the_shared_last_line_is_the_sign_off(self):
        fixtures = measure_fixtures(POSTS)
        assert fixtures["sign_off"] == "Rinse. Refill. Repeat."
        assert fixtures["sign_off_count"] == 3

    def test_a_phrase_in_every_post_is_recorded_exactly(self):
        phrases = [p for p, _ in measure_fixtures(POSTS)["phrases"]]
        assert "Here's the thing." in phrases, "curly and straight apostrophes are the same phrase"

    def test_the_sign_off_is_not_listed_twice(self):
        phrases = [p for p, _ in measure_fixtures(POSTS)["phrases"]]
        assert "Rinse. Refill. Repeat." not in phrases

    def test_a_line_in_only_one_post_is_not_a_fixture(self):
        phrases = [p for p, _ in measure_fixtures(POSTS)["phrases"]]
        assert "Spray. Wait. Wipe." not in phrases and "Let's not pretend." not in phrases

    def test_different_endings_give_no_sign_off(self):
        posts = [p.replace("Rinse. Refill. Repeat.", ending)
                 for p, ending in zip(POSTS, ("Thanks.", "See you soon.", "Bye for now."))]
        assert measure_fixtures(posts)["sign_off"] is None

    def test_one_document_is_not_enough_to_call_anything_a_habit(self):
        fixtures = measure_fixtures(POSTS[:1])
        assert fixtures["sign_off"] is None and fixtures["phrases"] == []


class TestSpelling:
    def test_british_brand(self):
        assert spelling_variety(POSTS)[0] == "british"

    def test_american_brand(self):
        assert spelling_variety(["My favorite color.", "We realized the color was off."])[0] == "american"

    def test_too_little_evidence_decides_nothing(self):
        assert spelling_variety(["A plain post with no telling words at all."])[0] is None

    def test_words_spelled_the_same_on_both_sides_are_not_evidence(self):
        """Humorous, honorary and analyses are British spellings too."""
        assert spelling_variety(["A humorous, honorary post.", "Two analyses."])[0] is None

    def test_respelling_keeps_case(self):
        text, changes = respell("Colorful bottles. We did the math. REALIZE it.", "british")
        assert text == "Colourful bottles. We did the maths. REALISE it."
        assert len(changes) == 3

    def test_a_name_from_the_source_is_left_alone(self):
        text, _ = respell("Join the Color Run in a colorful shirt.", "british", protected=["Color"])
        assert text == "Join the Color Run in a colourful shirt."

    def test_an_american_brand_is_respelled_the_other_way(self):
        assert respell("Our favourite colour.", "american")[0] == "Our favorite color."


class TestInTheBrain:
    def test_voice_spec_carries_the_fixtures(self):
        spec = render_spec(corpus_spec(POSTS))
        assert '- SIGN-OFF: "Rinse. Refill. Repeat."' in spec
        assert "Here's the thing." in spec
        assert "British English" in spec
        assert sign_off_from(spec) == "Rinse. Refill. Repeat."
        assert spelling_from(spec) == "british"

    def test_nothing_found_renders_nothing(self):
        assert render_fixtures({"documents": 3, "phrases": []}) == []


class TestTheSignOffCheck:
    BRAIN = render_spec(corpus_spec(POSTS))
    BODY = ("Open the cupboard and count the bottles. Here's the thing. Each one is mostly water, "
            "and the station refills your glass bottle for less.\n\n")

    def _sign_off_failures(self, draft):
        return [f for f in run_preflight_checks(draft, self.BRAIN) if "sign-off" in f["message"]]

    def test_a_draft_with_another_ending_is_sent_back(self):
        failures = self._sign_off_failures(self.BODY + "Bring. Fill. Tap. Go.")
        assert failures and '"Rinse. Refill. Repeat."' in failures[0]["message"]
        assert failures[0]["excerpt"] == "Bring. Fill. Tap. Go."

    def test_the_exact_sign_off_passes(self):
        assert not self._sign_off_failures(self.BODY + "Rinse. Refill. Repeat.")

    def test_markup_and_case_do_not_matter(self):
        assert not self._sign_off_failures(self.BODY + "**Rinse. refill. repeat.**")

    def test_a_sign_off_run_into_the_last_paragraph_still_counts(self):
        assert ends_with_sign_off(self.BODY + "See you there. Rinse. Refill. Repeat.",
                                  "Rinse. Refill. Repeat.")

    def test_no_sign_off_in_the_brain_means_no_check(self):
        assert not [f for f in run_preflight_checks(self.BODY + "Bye.", "# VOICE SPEC\n")
                    if "sign-off" in f["message"]]
