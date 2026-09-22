import pytest

from irodori_client.config import _DEFAULT_SYMBOLS, load_config


def test_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_empty_yaml_applies_defaults(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("", encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.tts.base_url == "http://localhost:8088"
    assert cfg.split.max_chars == 140
    assert cfg.mark.min_confidence == 0.5
    assert cfg.cleaning.symbols_remove == _DEFAULT_SYMBOLS


def test_overrides_are_loaded(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "tts:\n"
        "  voice: 2\n"
        "split:\n"
        "  max_chars: 0\n"
        "output:\n"
        "  dir: ./custom\n"
        "typesafe:\n"
        "  model: jev-test\n"
        "mark:\n"
        "  min_confidence: 0.7\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.tts.voice == 2
    assert cfg.split.max_chars == 0
    assert cfg.output.dir == "./custom"
    assert cfg.typesafe.model == "jev-test"
    assert cfg.mark.min_confidence == 0.7
