from conftest import FIXTURES

from irodori_client.cli import main


def _run(tmp_path, *args, extra_config=""):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(extra_config, encoding="utf-8")
    return main(["--config", str(cfg), *args])


def _record(monkeypatch):
    calls = []

    def fake_synth_one(text, cfg, split):
        calls.append((text, cfg.voice))
        return b"A"

    monkeypatch.setattr("irodori_client.tts.synth_one", fake_synth_one)
    return calls


def test_run_marked_filters_speakers(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    out = tmp_path / "out"
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(out), "--speakers", "f1",
    )
    assert rc == 0
    assert calls == [
        ("おはよう", "irodori_female_006"),
        ("元気？", "irodori_female_006"),
    ]
    assert (out / "mini_marked_cast" / "L0010.mp3").exists()
    assert (out / "mini_marked_cast" / "L0012.mp3").exists()
    assert not (out / "mini_marked_cast" / "L0011.mp3").exists()


def test_run_marked_per_character_voice(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(tmp_path / "out"),
    )
    assert rc == 0
    assert calls == [
        ("おはよう", "irodori_female_006"),
        ("今日はいい天気だな", "irodori_male_008"),
        ("元気？", "irodori_female_006"),
        ("ああ", "irodori_male_008"),
    ]


def test_run_marked_voice_override(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(tmp_path / "out"), "--voice", "fixed",
    )
    assert rc == 0
    assert {voice for _, voice in calls} == {"fixed"}


def test_run_marked_without_cast_falls_back_to_config_voice(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked.txt"),
        "-o", str(tmp_path / "out"),
    )
    assert rc == 0
    assert calls  # 4 marked lines
    assert {voice for _, voice in calls} == {"sample"}


def test_run_marked_speaker_case_and_separators(tmp_path, monkeypatch):
    calls = _record(monkeypatch)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(tmp_path / "out"), "--speakers", "F1",
    )
    assert rc == 0
    assert [text for text, _ in calls] == ["おはよう", "元気？"]


def test_run_marked_no_match_returns_zero(tmp_path, monkeypatch):
    _record(monkeypatch)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(tmp_path / "out"), "--speakers", "m9",
    )
    assert rc == 0


def test_run_marked_missing_file_returns_one(tmp_path):
    rc = _run(tmp_path, "run-marked", str(tmp_path / "nope.txt"))
    assert rc == 1


def test_run_marked_passes_caption_from_cast(tmp_path, monkeypatch):
    seen = []

    def fake_synth_one(text, cfg, split):
        seen.append((cfg.voice, dict(cfg.irodori)))
        return b"A"

    monkeypatch.setattr("irodori_client.tts.synth_one", fake_synth_one)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(tmp_path / "out"),
    )
    assert rc == 0
    f1 = [iro for voice, iro in seen if voice == "irodori_female_006"]
    m1 = [iro for voice, iro in seen if voice == "irodori_male_008"]
    assert f1 and all(iro.get("caption") == "囁くように" for iro in f1)
    assert m1 and all("caption" not in iro for iro in m1)


def test_run_marked_concat_writes_list_and_output(tmp_path, monkeypatch):
    monkeypatch.setattr("irodori_client.tts.synth_one", lambda text, cfg, split: b"A")
    calls = []

    def fake_concat(ffmpeg, list_path, output_path, log=None):
        calls.append((ffmpeg, list_path, output_path))
        output_path.write_bytes(b"CONCAT")

    monkeypatch.setattr("irodori_client.cli.concat_audio", fake_concat)
    out = tmp_path / "out"
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(out), "--concat",
    )
    assert rc == 0
    novel = out / "mini_marked_cast"
    entries = (novel / "list.txt").read_text(encoding="utf-8").splitlines()
    assert entries == [
        "file 'L0010.mp3'", "file 'L0011.mp3'",
        "file 'L0012.mp3'", "file 'L0013.mp3'",
    ]
    assert (novel / "mini_marked_cast.mp3").read_bytes() == b"CONCAT"
    assert calls and calls[0][0] == "ffmpeg"


def test_run_marked_concat_ffmpeg_override(tmp_path, monkeypatch):
    monkeypatch.setattr("irodori_client.tts.synth_one", lambda text, cfg, split: b"A")
    seen = []

    def fake_concat(ffmpeg, list_path, output_path, log=None):
        seen.append(ffmpeg)
        output_path.write_bytes(b"C")

    monkeypatch.setattr("irodori_client.cli.concat_audio", fake_concat)
    rc = _run(
        tmp_path, "run-marked", str(FIXTURES / "mini_marked_cast.txt"),
        "-o", str(tmp_path / "out"), "--concat",
        extra_config="concat:\n  ffmpeg: /opt/ffmpeg\n",
    )
    assert rc == 0
    assert seen == ["/opt/ffmpeg"]
