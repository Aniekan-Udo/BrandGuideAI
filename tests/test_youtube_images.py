"""Image adapters, upload checks and the image registry. No network: clients are fakes."""
import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from youtube.images import (
    GeneratedImage,
    ImageError,
    ImageInput,
    ImagePort,
    ImageRegistry,
    NanoBananaImage,
    SeedreamImage,
    WaveSpeedSeedreamImage,
    inspect_image,
    prepare_reference,
)


def png(width=512, height=512, color=(200, 120, 40), fmt="PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, format=fmt)
    return out.getvalue()


class TestUploads:
    @pytest.mark.parametrize("fmt, mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
    def test_accepts_common_formats(self, fmt, mime):
        assert inspect_image(png(fmt=fmt)) == (mime, 512, 512)

    @pytest.mark.parametrize("data, message", [
        (b"", "empty"),
        (b"not an image at all", "not a readable image"),
        (png(100, 400), "at least 256px"),
        (png(fmt="GIF"), "JPEG, PNG or WebP"),
    ])
    def test_rejects_bad_uploads(self, data, message):
        with pytest.raises(ValueError, match=message):
            inspect_image(data)

    def test_rejects_oversized_files(self, monkeypatch):
        monkeypatch.setattr("youtube.images.MAX_UPLOAD_BYTES", 100)
        with pytest.raises(ValueError, match="at most"):
            inspect_image(png())

    def test_references_are_shrunk_and_reencoded_without_metadata(self):
        source = io.BytesIO()
        image = Image.new("RGBA", (3000, 1500), (10, 20, 30, 255))
        exif = Image.Exif()
        exif[0x010F] = "SecretCam"  # camera make
        image.convert("RGB").save(source, format="JPEG", exif=exif)
        ref = prepare_reference(source.getvalue(), "Reference photo 1 of Maya")
        with Image.open(io.BytesIO(ref.data)) as out:
            assert out.format == "JPEG" and max(out.size) == 1024 and out.size == (1024, 512)
            assert not out.getexif(), "metadata must not leave the server"
        assert (ref.mime_type, ref.label) == ("image/jpeg", "Reference photo 1 of Maya")


class _FakeGenAI:
    def __init__(self, parts=None, finish="STOP"):
        self.calls = []
        self.parts = parts
        self.finish = finish

    @property
    def models(self):
        return self

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        parts = self.parts if self.parts is not None else [
            SimpleNamespace(inline_data=SimpleNamespace(data=png(1344, 768), mime_type="image/png"))]
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts), finish_reason=self.finish)],
            prompt_feedback=None)


class TestNanoBanana:
    def test_sends_labelled_references_then_the_prompt(self, monkeypatch):
        monkeypatch.delenv("YT_IMAGE_MODEL", raising=False)
        client = _FakeGenAI()
        port = NanoBananaImage(client=client)
        refs = [ImageInput(png(), "image/png", "Reference sheet for MAYA:"), ImageInput(png(), "image/png")]
        image = port.generate("Draw the bakery.", refs, "16:9")

        model, contents, config = client.calls[0]
        assert model == "gemini-3.1-flash-image"
        assert contents[0] == "Reference sheet for MAYA:"
        assert contents[-1] == "Draw the bakery."
        assert len(contents) == 4  # label, image, image (no label), prompt
        assert config.image_config.aspect_ratio == "16:9"
        assert config.response_modalities == ["IMAGE"]
        assert (image.width, image.height, image.mime_type, image.extension) == (1344, 768, "image/png", "png")

    def test_a_blocked_request_is_a_clear_error(self):
        port = NanoBananaImage(client=_FakeGenAI(parts=[SimpleNamespace(inline_data=None, text="no")],
                                                 finish="IMAGE_SAFETY"))
        with pytest.raises(ImageError, match="IMAGE_SAFETY"):
            port.generate("Draw.", [], "1:1")

    def test_validates_inputs_before_calling(self):
        client = _FakeGenAI()
        port = NanoBananaImage(client=client)
        with pytest.raises(ValueError):
            port.generate("", [], "16:9")
        with pytest.raises(ValueError):
            port.generate("Draw.", [], "4:3")
        with pytest.raises(ValueError):
            port.generate("Draw.", [ImageInput(b"x", "image/png")] * 15, "16:9")
        assert client.calls == []

    def test_price_can_be_overridden(self, monkeypatch):
        port = NanoBananaImage(client=_FakeGenAI())
        monkeypatch.delenv("YT_IMAGE_USD", raising=False)
        assert port.cost_usd(10) == pytest.approx(0.67)
        monkeypatch.setenv("YT_IMAGE_USD", "0.039")
        assert port.cost_usd(10) == pytest.approx(0.39)


class _FakeHTTP:
    def __init__(self, image_url):
        self.posts, self.gets = [], []
        self.image_url = image_url

    def post(self, url, json, headers):
        self.posts.append((url, json, headers))
        return SimpleNamespace(status_code=200, json=lambda: {"images": [{"url": self.image_url, "content_type": "image/png"}]},
                               text="")

    def get(self, url):
        self.gets.append(url)
        return SimpleNamespace(status_code=200, content=png(768, 1344), headers={"content-type": "image/png"})


class TestSeedream:
    def test_references_become_data_uris_and_labels_go_into_the_prompt(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "fal-test")
        data_uri = "data:image/png;base64," + base64.b64encode(png(768, 1344)).decode()
        http = _FakeHTTP(data_uri)
        image = SeedreamImage(http=http).generate(
            "Draw Maya.", [ImageInput(b"abc", "image/jpeg", "Reference sheet for MAYA:")], "9:16")
        url, body, headers = http.posts[0]
        assert url == SeedreamImage.EDIT_URL
        assert headers == {"Authorization": "Key fal-test"}
        assert body["image_urls"] == ["data:image/jpeg;base64," + base64.b64encode(b"abc").decode()]
        assert body["prompt"].startswith("Image 1: Reference sheet for MAYA:")
        assert body["image_size"] == "portrait_16_9"
        assert (image.width, image.height) == (768, 1344)
        assert http.gets == []

    def test_text_only_uses_text_to_image_and_downloads_urls(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "fal-test")
        http = _FakeHTTP("https://cdn.example/image.png")
        SeedreamImage(http=http).generate("A street at dawn.", [], "16:9")
        assert http.posts[0][0] == SeedreamImage.TEXT_URL
        assert "image_urls" not in http.posts[0][1]
        assert http.gets == ["https://cdn.example/image.png"]

    def test_errors(self, monkeypatch):
        monkeypatch.delenv("FAL_KEY", raising=False)
        with pytest.raises(ImageError, match="FAL_KEY"):
            SeedreamImage(http=_FakeHTTP("x")).generate("Draw.", [], "1:1")
        monkeypatch.setenv("FAL_KEY", "k")
        failing = _FakeHTTP("x")
        failing.post = lambda url, json, headers: SimpleNamespace(status_code=422, text="bad input", json=lambda: {})
        with pytest.raises(ImageError, match="422"):
            SeedreamImage(http=failing).generate("Draw.", [], "1:1")


def _resp(status=200, payload=None, content=b"", headers=None, text=""):
    return SimpleNamespace(status_code=status, json=lambda: payload or {}, content=content,
                           headers=headers or {}, text=text)


class _FakeWaveSpeed:
    """Answers WaveSpeed's upload, submit, result and download calls; records each request."""

    def __init__(self, statuses=("processing", "completed"), submit_status=200):
        self.uploads, self.submits, self.gets = [], [], []
        self.statuses = list(statuses)
        self.submit_status = submit_status

    def post(self, url, headers, json=None, files=None):
        if url.endswith("/media/upload/binary"):
            self.uploads.append((url, files, headers))
            return _resp(payload={"data": {"download_url": f"https://ws/ref{len(self.uploads)}.jpg"}})
        self.submits.append((url, json, headers))
        if self.submit_status != 200:
            return _resp(self.submit_status, text="bad input")
        return _resp(payload={"data": {"id": "p1", "status": "created"}})

    def get(self, url, headers=None):
        self.gets.append(url)
        if url.endswith("/predictions/p1/result"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            outputs = ["https://ws/out.png"] if status == "completed" else []
            return _resp(payload={"data": {"status": status, "outputs": outputs, "error": "nsfw" if status == "failed" else ""}})
        return _resp(content=png(1536, 2688), headers={"content-type": "image/png"})


class TestSeedreamWaveSpeed:
    @pytest.fixture(autouse=True)
    def key(self, monkeypatch):
        monkeypatch.setenv("WAVESPEED_API_KEY", "ws-test")
        monkeypatch.delenv("YT_IMAGE_SIZE", raising=False)

    def test_uploads_references_submits_polls_and_downloads(self):
        http = _FakeWaveSpeed()
        image = WaveSpeedSeedreamImage(http=http, sleep=lambda s: None).generate(
            "Draw Maya.", [ImageInput(b"abc", "image/jpeg", "Reference sheet for MAYA:")], "9:16")
        assert len(http.uploads) == 1 and http.uploads[0][2] == {"Authorization": "Bearer ws-test"}
        url, body, headers = http.submits[0]
        assert url == WaveSpeedSeedreamImage.API + WaveSpeedSeedreamImage.EDIT_PATH
        assert body["images"] == ["https://ws/ref1.jpg"]
        assert body["prompt"].startswith("Image 1: Reference sheet for MAYA:")
        assert body["size"] == "1536*2688"
        assert http.gets[-1] == "https://ws/out.png"
        assert (image.width, image.height) == (1536, 2688)

    def test_text_only_uses_text_to_image_and_size_follows_env(self, monkeypatch):
        monkeypatch.setenv("YT_IMAGE_SIZE", "1K")
        http = _FakeWaveSpeed(statuses=("completed",))
        WaveSpeedSeedreamImage(http=http, sleep=lambda s: None).generate("A street at dawn.", [], "16:9")
        url, body, _ = http.submits[0]
        assert url == WaveSpeedSeedreamImage.API + WaveSpeedSeedreamImage.TEXT_PATH
        assert "images" not in body and body["size"] == "1344*768"
        assert http.uploads == []

    def test_a_reference_used_in_every_shot_is_uploaded_once(self):
        http = _FakeWaveSpeed(statuses=("completed",))
        port = WaveSpeedSeedreamImage(http=http, sleep=lambda s: None)
        sheet = ImageInput(b"sheet", "image/png", "Reference sheet for MAYA:")
        for _ in range(3):
            port.generate("Shot.", [sheet], "16:9")
        assert len(http.uploads) == 1
        assert all(body["images"] == ["https://ws/ref1.jpg"] for _, body, _ in http.submits)

    def test_errors(self, monkeypatch):
        with pytest.raises(ImageError, match="422"):
            WaveSpeedSeedreamImage(http=_FakeWaveSpeed(submit_status=422), sleep=lambda s: None).generate("Draw.", [], "1:1")
        with pytest.raises(ImageError, match="failed: nsfw"):
            WaveSpeedSeedreamImage(http=_FakeWaveSpeed(statuses=("failed",)), sleep=lambda s: None).generate("Draw.", [], "1:1")
        monkeypatch.setattr(WaveSpeedSeedreamImage, "TIMEOUT_S", 0)
        with pytest.raises(ImageError, match="did not finish"):
            WaveSpeedSeedreamImage(http=_FakeWaveSpeed(statuses=("processing",)), sleep=lambda s: None).generate("Draw.", [], "1:1")
        monkeypatch.delenv("WAVESPEED_API_KEY")
        with pytest.raises(ImageError, match="WAVESPEED_API_KEY"):
            WaveSpeedSeedreamImage(http=_FakeWaveSpeed()).generate("Draw.", [], "1:1")

    def test_price_and_registry(self, monkeypatch):
        monkeypatch.delenv("YT_IMAGE_USD", raising=False)
        assert WaveSpeedSeedreamImage().cost_usd(80) == pytest.approx(2.16)
        monkeypatch.setattr(ImageRegistry, "_instances", {})
        monkeypatch.setenv("YT_IMAGE_PROVIDER", "seedream_wavespeed")
        assert isinstance(ImageRegistry.get(), WaveSpeedSeedreamImage)
        monkeypatch.delenv("WAVESPEED_API_KEY")
        assert WaveSpeedSeedreamImage.missing_env() == ["WAVESPEED_API_KEY"]


class TestRegistry:
    @pytest.fixture(autouse=True)
    def clean(self, monkeypatch):
        monkeypatch.setattr(ImageRegistry, "_instances", {})
        monkeypatch.delenv("YT_IMAGE_PROVIDER", raising=False)

    def test_adapters_implement_the_port(self):
        for adapter in ImageRegistry.PROVIDERS.values():
            assert issubclass(adapter, ImagePort)
            assert adapter.max_characters <= adapter.max_references

    def test_defaults_to_nano_banana_and_switches_by_env(self, monkeypatch):
        assert isinstance(ImageRegistry.get(), NanoBananaImage)
        monkeypatch.setattr(ImageRegistry, "_instances", {})
        monkeypatch.setenv("YT_IMAGE_PROVIDER", "seedream")
        assert isinstance(ImageRegistry.get(), SeedreamImage)

    def test_unknown_provider(self, monkeypatch):
        with pytest.raises(ValueError, match="Unknown image provider"):
            ImageRegistry.get("midjourney")
        monkeypatch.setenv("YT_IMAGE_PROVIDER", "nope")
        with pytest.raises(ValueError, match="YT_IMAGE_PROVIDER"):
            ImageRegistry.default_provider()

    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("FAL_KEY", raising=False)
        assert SeedreamImage.missing_env() == ["FAL_KEY"]


def test_generated_image_extension():
    assert GeneratedImage(b"", "image/jpeg", 1, 1).extension == "jpg"


class TestRateLimits:
    def test_retries_rate_limits_with_increasing_waits_then_succeeds(self, monkeypatch):
        from youtube.images import with_rate_limit_retry

        monkeypatch.delenv("YT_IMAGE_MAX_RETRIES", raising=False)
        attempts, waits = [], []

        def call():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return "image"

        assert with_rate_limit_retry(call, lambda e: "429" in str(e), sleep=waits.append) == "image"
        assert waits == [15, 30]

    def test_gives_up_after_the_retry_limit_with_a_clear_error(self, monkeypatch):
        from youtube.images import RateLimited, with_rate_limit_retry

        monkeypatch.setenv("YT_IMAGE_MAX_RETRIES", "2")
        waits = []

        def always_limited():
            raise RuntimeError("429")

        with pytest.raises(RateLimited, match="after 2 retries"):
            with_rate_limit_retry(always_limited, lambda e: True, sleep=waits.append)
        assert waits == [15, 30]

    def test_other_errors_are_not_retried(self):
        from youtube.images import with_rate_limit_retry

        waits = []
        with pytest.raises(ValueError):
            with_rate_limit_retry(lambda: (_ for _ in ()).throw(ValueError("bad prompt")),
                                  lambda e: False, sleep=waits.append)
        assert waits == []

    def test_nano_banana_retries_a_429_from_vertex(self, monkeypatch):
        import youtube.images as images

        monkeypatch.setattr(images.time, "sleep", lambda s: None)
        client = _FakeGenAI()
        real = client.generate_content
        failures = []

        def flaky(model, contents, config):
            if not failures:
                failures.append(1)
                error = RuntimeError("Resource has been exhausted")
                error.code = 429
                raise error
            return real(model, contents, config)

        client.generate_content = flaky
        image = NanoBananaImage(client=client).generate("Draw.", [], "16:9")
        assert image.width == 1344 and failures == [1]


class TestNetworkRetry:
    """A finished clip or image is already paid for, so a network blip must not lose it."""

    def _http(self, *answers):
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            answer = answers[len(calls) - 1]
            if isinstance(answer, Exception):
                raise answer
            return SimpleNamespace(status_code=answer)
        return SimpleNamespace(get=get), calls

    def test_retries_network_errors_and_server_errors_then_succeeds(self):
        import httpx
        from youtube.images import get_with_retry

        http, calls = self._http(httpx.ConnectError("[Errno -5] No address associated with hostname"), 503, 200)
        waits = []
        assert get_with_retry(http, "https://cdn/clip.mp4", sleep=waits.append).status_code == 200
        assert len(calls) == 3 and waits == [2, 5]

    def test_client_errors_are_returned_at_once(self):
        from youtube.images import get_with_retry

        http, calls = self._http(404)
        assert get_with_retry(http, "https://cdn/x", sleep=lambda s: None).status_code == 404
        assert len(calls) == 1

    def test_gives_up_after_four_attempts(self):
        import httpx
        from youtube.images import get_with_retry

        http, calls = self._http(*[httpx.ConnectError("down")] * 4)
        with pytest.raises(httpx.ConnectError):
            get_with_retry(http, "https://cdn/x", sleep=lambda s: None)
        assert len(calls) == 4
        http, calls = self._http(500, 500, 500, 500)
        assert get_with_retry(http, "https://cdn/x", sleep=lambda s: None).status_code == 500
        assert len(calls) == 4

    def test_infinitetalk_keeps_a_paid_clip_through_a_dns_failure(self, monkeypatch):
        import httpx
        from youtube.avatar import InfiniteTalkAvatar

        monkeypatch.setenv("WAVESPEED_API_KEY", "w")
        state = {"downloads": 0}

        class Http:
            def post(self, url, **kwargs):
                if url.endswith("/media/upload/binary"):
                    return SimpleNamespace(status_code=200, json=lambda: {"data": {"download_url": "https://ws/in"}})
                return SimpleNamespace(status_code=200, json=lambda: {"data": {"id": "p1"}})

            def get(self, url, **kwargs):
                if url.endswith("/predictions/p1/result"):
                    return SimpleNamespace(status_code=200, json=lambda: {"data": {
                        "status": "completed", "outputs": ["https://cdn.example/clip.mp4"]}})
                state["downloads"] += 1
                if state["downloads"] == 1:
                    raise httpx.ConnectError("[Errno -5] No address associated with hostname")
                return SimpleNamespace(status_code=200, content=b"mp4")

        clip = InfiniteTalkAvatar(http=Http(), sleep=lambda s: None).animate(b"i", "image/png", b"w", 4.5)
        assert clip.video == b"mp4" and state["downloads"] == 2
