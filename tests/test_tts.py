import pytest

from irodori_client.config import SplitConfig, TTSConfig
from irodori_client.extractor import ExtractedLine
from irodori_client.tts import (
    build_headers,
    build_payload,
    output_paths,
    synth_iter,
    synth_one,
)


class _Resp:
    def __init__(self, status_code, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


def test_build_payload_disables_server_chunking():
    cfg = TTSConfig(voice=2, irodori={"foo": None, "bar": 1})
    payload = build_payload("hello", cfg, SplitConfig(max_chars=140))
    assert payload["voice"] == "2"
    assert payload["irodori"] == {"bar": 1, "chunking_enabled": False}


def test_build_payload_no_irodori_key_when_empty():
    cfg = TTSConfig(irodori={})
    payload = build_payload("hello", cfg, SplitConfig(max_chars=0))
    assert "irodori" not in payload


def test_build_headers_api_key():
    assert "Authorization" in build_headers(TTSConfig(api_key="t"))
    assert "Authorization" not in build_headers(TTSConfig(api_key=None))


def test_synth_one_returns_bytes(monkeypatch):
    monkeypatch.setattr(
        "irodori_client.tts.requests.post",
        lambda *a, **k: _Resp(200, content=b"AUDIO"),
    )
    assert synth_one("hi", TTSConfig(), SplitConfig()) == b"AUDIO"


def test_synth_one_client_error_raises(monkeypatch):
    monkeypatch.setattr(
        "irodori_client.tts.requests.post",
        lambda *a, **k: _Resp(400, text="bad"),
    )
    with pytest.raises(RuntimeError):
        synth_one("hi", TTSConfig(), SplitConfig(), max_retries=0)


def test_synth_iter_splits_and_names_files(tmp_path, monkeypatch):
    monkeypatch.setattr("irodori_client.tts.synth_one", lambda text, cfg, split: b"A")
    cfg = TTSConfig(response_format="mp3")
    items = [ExtractedLine(line=7, text="あ。い。う。", raw="")]
    success = synth_iter(items, tmp_path, cfg, SplitConfig(max_chars=4), "novel1")
    assert success == 2
    assert (tmp_path / "novel1" / "L0007_1.mp3").exists()
    assert (tmp_path / "novel1" / "L0007_2.mp3").exists()


def test_synth_iter_single_chunk_name(tmp_path, monkeypatch):
    monkeypatch.setattr("irodori_client.tts.synth_one", lambda text, cfg, split: b"A")
    cfg = TTSConfig(response_format="mp3")
    items = [ExtractedLine(line=3, text="短い", raw="")]
    success = synth_iter(items, tmp_path, cfg, SplitConfig(max_chars=140), "novel1")
    assert success == 1
    assert (tmp_path / "novel1" / "L0003.mp3").exists()


def test_synth_iter_per_item_voice(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "irodori_client.tts.synth_one",
        lambda text, cfg, split: calls.append(cfg.voice) or b"A",
    )
    items = [ExtractedLine(line=5, text="abc", raw="")]
    synth_iter(
        items, tmp_path, TTSConfig(), SplitConfig(), "n",
        overrides_resolver=lambda item: {"voice": "vX"},
    )
    assert calls == ["vX"]


def test_synth_iter_caption_override(tmp_path, monkeypatch):
    seen = []

    def fake(text, cfg, split):
        seen.append(dict(cfg.irodori))
        return b"A"

    monkeypatch.setattr("irodori_client.tts.synth_one", fake)
    cfg = TTSConfig(irodori={"caption": "global"})
    items = [
        ExtractedLine(line=1, text="a", raw=""),
        ExtractedLine(line=2, text="b", raw=""),
    ]
    synth_iter(
        items, tmp_path, cfg, SplitConfig(max_chars=0), "n",
        overrides_resolver=lambda item: {
            "caption": "line" if item.line == 1 else None
        },
    )
    assert seen[0].get("caption") == "line"
    assert "caption" not in seen[1]


def test_output_paths_order(tmp_path):
    items = [ExtractedLine(line=7, text="あ。い。う。", raw="")]
    names = [
        p.name
        for p in output_paths(
            items, tmp_path, TTSConfig(response_format="mp3"),
            SplitConfig(max_chars=4), "n",
        )
    ]
    assert names == ["L0007_1.mp3", "L0007_2.mp3"]


def test_synth_iter_skip_existing(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "irodori_client.tts.synth_one",
        lambda text, cfg, split: calls.append(text) or b"A",
    )
    base = tmp_path / "n"
    base.mkdir()
    (base / "L0007_1.mp3").write_bytes(b"OLD")
    items = [ExtractedLine(line=7, text="あ。い。う。", raw="")]
    success = synth_iter(
        items, tmp_path, TTSConfig(), SplitConfig(max_chars=4), "n",
        skip_existing=True,
    )
    assert success == 2
    assert len(calls) == 1
