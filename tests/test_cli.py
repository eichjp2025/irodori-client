from conftest import FIXTURES

from irodori_client.cli import main


def _run(tmp_path, *args, extra_config=""):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(extra_config, encoding="utf-8")
    return main(["--config", str(cfg), *args])


def test_mark_missing_novel_returns_one(tmp_path):
    rc = _run(tmp_path, "mark", str(tmp_path / "missing.txt"))
    assert rc == 1


def test_mark_dry_run_makes_no_file(tmp_path):
    out = tmp_path / "out"
    rc = _run(
        tmp_path, "mark", str(FIXTURES / "mini_novel.txt"),
        "-o", str(out), "--dry-run",
    )
    assert rc == 0
    assert not (out / "mini_novel" / "mini_novel.txt").exists()


def test_mark_writes_to_novel_id_dir(tmp_path, monkeypatch):
    def fake_system_one(state, questions, cfg, log=None, debug=None):
        return {"answers": {
            k: {"type": "choice", "choice": "f1", "confidence": 0.9,
                "probabilities": {"f1": 0.9}}
            for k in questions
        }}

    monkeypatch.setattr("irodori_client.attributor.system_one", fake_system_one)
    out = tmp_path / "out"
    rc = _run(tmp_path, "mark", str(FIXTURES / "mini_novel.txt"), "-o", str(out))
    assert rc == 0
    marked = out / "mini_novel" / "mini_novel.txt"
    report = out / "mini_novel" / "mini_novel.report.json"
    assert marked.exists() and report.exists()
    assert "「おはよう」f1" in marked.read_text(encoding="utf-8")


def test_mark_init_header(tmp_path):
    src = tmp_path / "my_novel.txt"
    src.write_text("第一話\n\n「こんにちは」\n", encoding="utf-8")
    out = tmp_path / "out"
    rc = _run(tmp_path, "mark", str(src), "-o", str(out), "--init-header")
    assert rc == 0
    text = (out / "my_novel" / "my_novel.txt").read_text(encoding="utf-8")
    assert text.startswith("<!--\nformat: irodori")
    assert "f1:" in text and "f2:" in text and "m1:" in text
    assert "通常シーン" in text and "エッチなシーン" in text
    assert text.endswith("第一話\n\n「こんにちは」\n")


def test_mark_init_header_rejects_existing(tmp_path):
    out = tmp_path / "out"
    rc = _run(
        tmp_path, "mark", str(FIXTURES / "mini_novel.txt"),
        "-o", str(out), "--init-header",
    )
    assert rc == 1
    assert not (out / "mini_novel" / "mini_novel.txt").exists()
