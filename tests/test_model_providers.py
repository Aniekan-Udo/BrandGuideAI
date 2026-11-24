"""The LLM provider adapters and the switch in LLMSingleton.

Every LLM call goes through model.LLMSingleton, which picks one LLMProvider
adapter from LLM_PROVIDER. These tests pin that down without any network call:
chat models are constructed, never invoked.
"""
import pytest
from langchain_core.messages import AIMessage

from model import (
    ChatModelHandle,
    ClaudeProvider,
    GeminiAPIProvider,
    GroqProvider,
    LLMProvider,
    LLMSingleton,
    OpenAICompatibleProvider,
    VertexAIProvider,
)
from utils.llm_output import message_text

PROVIDER_ENV = [
    "LLM_PROVIDER", "LLM_MODEL", "GEMINI_MODEL", "OPENAI_BASE_URL", "GEMINI_BASE_URL",
] + [f"{prefix}_{mode.upper()}"
     for prefix in ("LLM_TEMPERATURE", "LLM_MAX_TOKENS", "LLM_MODEL", "LLM_PROVIDER", "LLM_TIMEOUT")
     for mode in LLMSingleton.MODE_TEMPERATURES]


@pytest.fixture
def env(monkeypatch):
    """A clean provider environment; returns a setter for provider variables."""
    def configure(**values):
        for var in PROVIDER_ENV:
            monkeypatch.delenv(var, raising=False)
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    configure()
    return configure


class TestAdapterContract:
    def test_base_class_is_abstract(self):
        with pytest.raises(TypeError):
            LLMProvider()

    @pytest.mark.parametrize("adapter", [
        VertexAIProvider, GroqProvider, ClaudeProvider, OpenAICompatibleProvider, GeminiAPIProvider,
    ])
    def test_every_adapter_declares_itself(self, adapter):
        assert issubclass(adapter, LLMProvider)
        assert adapter.name and adapter.default_model and adapter.required_env

    def test_every_registered_provider_is_an_adapter(self):
        assert set(LLMSingleton.PROVIDERS) == {"vertex_ai", "groq", "claude", "openai", "gemini"}
        for name, adapter in LLMSingleton.PROVIDERS.items():
            assert adapter.name == name

    def test_missing_env_reports_the_adapters_credentials(self, env, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert GroqProvider.missing_env() == ["GROQ_API_KEY"]
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        assert GroqProvider.missing_env() == []


class TestSwitch:
    def test_defaults_to_vertex(self, env):
        assert LLMSingleton.provider_class() is VertexAIProvider

    @pytest.mark.parametrize("value, adapter", [
        ("vertex_ai", VertexAIProvider),
        ("groq", GroqProvider),
        ("claude", ClaudeProvider),
        ("anthropic", ClaudeProvider),
        ("GROQ", GroqProvider),
        ("openai", OpenAICompatibleProvider),
        ("gemini", GeminiAPIProvider),
        ("google_ai_studio", GeminiAPIProvider),
    ])
    def test_llm_provider_selects_the_adapter(self, env, value, adapter):
        env(LLM_PROVIDER=value)
        assert LLMSingleton.provider_class() is adapter

    def test_unregistered_provider_is_a_clear_error(self, env):
        env(LLM_PROVIDER="mistral")
        with pytest.raises(ValueError, match="LLM_PROVIDER must be one of"):
            LLMSingleton.provider_class()

    def test_mode_tuning_reaches_the_adapter(self, env):
        env(LLM_PROVIDER="groq", LLM_MAX_TOKENS_SYNTHESIS="16384")
        synthesis = LLMSingleton.create_provider("synthesis")
        extraction = LLMSingleton.create_provider("extraction")
        assert (synthesis.max_tokens, synthesis.temperature) == (16384, 0.3)
        assert (extraction.max_tokens, extraction.temperature) == (8192, 0.1)

    def test_llm_model_overrides_the_default(self, env):
        env(LLM_PROVIDER="claude")
        assert LLMSingleton.create_provider().model == "claude-opus-5-5"
        env(LLM_PROVIDER="claude", LLM_MODEL="claude-haiku-4-5")
        assert LLMSingleton.create_provider().model == "claude-haiku-4-5"

    def test_gemini_model_still_honoured_on_vertex(self, env):
        env(GEMINI_MODEL="gemini-2.5-pro")
        assert LLMSingleton.create_provider().model == "gemini-2.5-pro"

    def test_one_mode_can_run_a_stronger_model_than_the_rest(self, env):
        """The judge decides whether a draft sounds like the brand, and per-
        document extraction is checked in code afterwards. Without this, making
        the first stronger made the second stronger too — the highest-volume,
        most mechanical call in the system."""
        env(LLM_MODEL="gemini-2.5-flash", LLM_MODEL_ENFORCEMENT="gemini-2.5-pro")
        assert LLMSingleton.create_provider("enforcement").model == "gemini-2.5-pro"
        assert LLMSingleton.create_provider("extraction").model == "gemini-2.5-flash"
        assert LLMSingleton.create_provider("generation").model == "gemini-2.5-flash"

    def test_the_per_mode_variable_outranks_the_shared_one(self, env):
        env(LLM_PROVIDER="claude", LLM_MODEL="claude-haiku-4-5",
            LLM_MODEL_SYNTHESIS="claude-opus-5")
        assert LLMSingleton.create_provider("synthesis").model == "claude-opus-5"
        assert LLMSingleton.create_provider("extraction").model == "claude-haiku-4-5"

    def test_setting_nothing_changes_nothing(self, env):
        """A deployment that sets no per-mode variable keeps the model it has
        today, on every mode, and the bill it has today."""
        env(LLM_PROVIDER="claude")
        assert {LLMSingleton.create_provider(m).model for m in LLMSingleton.MODE_TEMPERATURES} == {
            "claude-opus-5-5"
        }

    def test_a_built_in_default_applies_where_the_environment_is_silent(self, env, monkeypatch):
        monkeypatch.setitem(LLMSingleton.MODE_MODELS, "enforcement", "gemini-2.5-pro")
        env()
        assert LLMSingleton.create_provider("enforcement").model == "gemini-2.5-pro"
        assert LLMSingleton.create_provider("extraction").model == "gemini-2.5-flash"

    def test_the_environment_still_beats_a_built_in_default(self, env, monkeypatch):
        monkeypatch.setitem(LLMSingleton.MODE_MODELS, "enforcement", "gemini-2.5-pro")
        env(LLM_MODEL_ENFORCEMENT="gemini-2.5-flash")
        assert LLMSingleton.create_provider("enforcement").model == "gemini-2.5-flash"


class TestEachModeOnItsOwnProvider:
    """A frontier writer, a judge from another model family and a free model
    for the high-volume extraction, chosen per mode in the environment."""

    def test_one_mode_moves_to_another_provider(self, env):
        env(LLM_PROVIDER="groq", LLM_PROVIDER_GENERATION="claude")
        assert LLMSingleton.provider_class("generation") is ClaudeProvider
        assert LLMSingleton.provider_class("extraction") is GroqProvider
        assert LLMSingleton.provider_class() is GroqProvider

    def test_writer_and_judge_on_different_families(self, env):
        env(LLM_PROVIDER="groq", LLM_PROVIDER_GENERATION="claude",
            LLM_PROVIDER_ENFORCEMENT="gemini", LLM_MODEL_ENFORCEMENT="gemini-2.5-pro")
        writer = LLMSingleton.create_provider("generation")
        judge = LLMSingleton.create_provider("enforcement")
        assert (writer.name, writer.model) == ("claude", "claude-opus-5-5")
        assert (judge.name, judge.model) == ("gemini", "gemini-2.5-pro")

    def test_a_moved_mode_does_not_inherit_the_shared_model(self, env):
        """LLM_MODEL names a Groq model here; sending it to Anthropic would fail."""
        env(LLM_PROVIDER="groq", LLM_MODEL="openai/gpt-oss-120b", LLM_PROVIDER_GENERATION="claude")
        assert LLMSingleton.create_provider("generation").model == "claude-opus-5-5"
        assert LLMSingleton.create_provider("extraction").model == "openai/gpt-oss-120b"

    def test_a_moved_mode_ignores_built_in_mode_models_too(self, env, monkeypatch):
        monkeypatch.setitem(LLMSingleton.MODE_MODELS, "generation", "gemini-2.5-pro")
        env(LLM_PROVIDER_GENERATION="claude")
        assert LLMSingleton.create_provider("generation").model == "claude-opus-5-5"

    def test_naming_the_shared_provider_per_mode_keeps_the_shared_model(self, env):
        env(LLM_PROVIDER="groq", LLM_MODEL="openai/gpt-oss-120b", LLM_PROVIDER_GENERATION="GROQ")
        assert LLMSingleton.create_provider("generation").model == "openai/gpt-oss-120b"

    def test_an_unknown_mode_provider_names_its_variable(self, env):
        env(LLM_PROVIDER_ENFORCEMENT="mistral")
        with pytest.raises(ValueError, match="LLM_PROVIDER_ENFORCEMENT must be one of"):
            LLMSingleton.provider_class("enforcement")

    def test_providers_in_use_lists_every_mode(self, env):
        env(LLM_PROVIDER="groq", LLM_PROVIDER_SYNTHESIS="openai")
        routing = LLMSingleton.providers_in_use()
        assert set(routing) == set(LLMSingleton.MODE_TEMPERATURES)
        assert routing["synthesis"] is OpenAICompatibleProvider
        assert routing["generation"] is GroqProvider

    def test_timeout_can_be_raised_for_one_mode(self, env):
        """Frontier reasoning models can need longer than 60s on a long draft."""
        env(LLM_TIMEOUT_GENERATION="240")
        assert LLMSingleton.create_provider("generation").timeout == 240
        assert LLMSingleton.create_provider("extraction").timeout != 240

    def test_setting_no_mode_provider_changes_nothing(self, env):
        env(LLM_PROVIDER="groq")
        assert set(LLMSingleton.providers_in_use().values()) == {GroqProvider}


class TestAdapters:
    def test_vertex_builds_chat_vertex_ai(self, env, monkeypatch):
        monkeypatch.setenv("PROJECT_ID", "test-project")
        llm = VertexAIProvider(max_tokens=1024).to_langchain()
        assert type(llm).__name__ == "ChatVertexAI"
        assert (llm.project, llm.max_output_tokens) == ("test-project", 1024)

    def test_groq_builds_chat_groq(self, env, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        llm = GroqProvider(temperature=0.2, max_tokens=2048).to_langchain()
        assert type(llm).__name__ == "ChatGroq"
        assert (llm.model_name, llm.temperature, llm.max_tokens) == (
            "llama-3.3-70b-versatile", 0.2, 2048)

    def test_claude_builds_chat_anthropic(self, env, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        llm = ClaudeProvider(model="claude-haiku-4-5", temperature=0.2).to_langchain()
        assert type(llm).__name__ == "ChatAnthropic"
        assert (llm.model, llm.temperature) == ("claude-haiku-4-5", 0.2)

    @pytest.mark.parametrize("name, accepts", [
        ("claude-opus-5", False),
        ("claude-sonnet-5", False),
        ("claude-opus-4-7", False),
        ("claude-opus-5-5", False),
        ("claude-haiku-5-5", False),
        ("claude-sonnet-4-6", True),
        ("claude-haiku-4-5", True),
    ])
    def test_claude_omits_temperature_where_rejected(self, env, monkeypatch, name, accepts):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        provider = ClaudeProvider(model=name, temperature=0.7)
        assert provider.supports_temperature() is accepts
        assert provider.to_langchain().temperature == (0.7 if accepts else None)


    def test_openai_builds_chat_openai(self, env, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        llm = OpenAICompatibleProvider(model="gpt-4.1", temperature=0.2, max_tokens=2048).to_langchain()
        assert type(llm).__name__ == "ChatOpenAI"
        assert (llm.model_name, llm.temperature, llm.max_tokens) == ("gpt-4.1", 0.2, 2048)

    def test_openai_base_url_points_at_any_compatible_api(self, env, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        env(OPENAI_BASE_URL="https://openrouter.ai/api/v1")
        llm = OpenAICompatibleProvider(model="deepseek/deepseek-chat").to_langchain()
        assert llm.openai_api_base == "https://openrouter.ai/api/v1"

    @pytest.mark.parametrize("name, accepts", [
        ("gpt-5", False),
        ("o3", False),
        ("openai/gpt-5", False),
        ("gpt-4.1", True),
        ("deepseek/deepseek-chat", True),
    ])
    def test_openai_omits_temperature_where_rejected(self, name, accepts):
        assert OpenAICompatibleProvider(model=name).supports_temperature() is accepts

    def test_gemini_uses_its_own_key_and_googles_endpoint(self, env, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        env(OPENAI_BASE_URL="https://openrouter.ai/api/v1")
        llm = GeminiAPIProvider().to_langchain()
        assert llm.openai_api_base.startswith("https://generativelanguage.googleapis.com/")
        assert llm.openai_api_key.get_secret_value() == "gemini-key"
        assert llm.model_name == "gemini-2.5-flash"


class TestTextContent:
    def test_content_blocks_flatten_to_text(self):
        blocks = [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "world"},
        ]
        assert message_text(blocks) == "Hello world"

    def test_handle_returns_string_content(self):
        class _Blocks:
            def invoke(self, input, config=None, **kwargs):
                return AIMessage(content=[{"type": "thinking", "thinking": "x"},
                                          {"type": "text", "text": "done"}])

        handle = ChatModelHandle(_Blocks(), ClaudeProvider())
        assert handle.invoke("prompt").content == "done"
