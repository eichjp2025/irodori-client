import json

from conftest import FIXTURES

from irodori_client.cli import main
from irodori_client.debug import DebugWriter

_dumps = json.dumps


class _Resp:
    def __init__(self, status_code, payload=None, text="", headers=None, reason="OK"):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}
        self.reason = reason

    def json(self):
        return self._payload


def test_debug_writer_creates_files(tmp_path):
    writer = DebugWriter(tmp_path, run_id="run1")
    idx = writer.begin_request({
        "state": "line1\nline2",
        "model": "m",
        "questions": {"L1": {"type": "choice"}},
    })
    writer.http_attempt(
        idx, 1,
        request={
            "method": "POST",
            "url": "https://example/v1/systemone",
            "headers": {"Authorization": "Bearer <redacted>"},
            "body_text": "{}",
            "body_json": {},
        },
        response={
            "status_code": 200, "reason": "OK", "headers": {},
            "body_text": "{}", "body_json": {}, "elapsed_ms": 1.0,
        },
    )
    writer.response(idx, {"answers": {}})
    writer.meta({"type": "mark"})

    run = tmp_path / "run1"
    assert (run / "000_meta.json").exists()
    assert (run / "001_request.json").exists()
    assert (run / "001_state.txt").read_text(encoding="utf-8") == "line1\nline2\n"
    assert (run / "001_questions.pretty.json").exists()
    assert (run / "001_http.json").exists()
    assert (run / "001_response.json").exists()

    http = json.loads((run / "001_http.json").read_text(encoding="utf-8"))
    assert http["attempts"][0]["attempt"] == 1
    assert http["attempts"][0]["response"]["status_code"] == 200


def test_debug_writer_disabled_writes_nothing(tmp_path):
    writer = DebugWriter(tmp_path, run_id="run1", enabled=False)
    writer.begin_request({"state": "x"})
    assert not (tmp_path / "run1").exists()


def test_mark_debug_writes_all_http_info(tmp_path, monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        answers = {
            key: {
                "type": "choice",
                "choice": "f1",
                "confidence": 0.9,
                "probabilities": {"f1": 0.9, "m1": 0.1},
            }
            for key in json["questions"]
        }
        body = {"model": "jev-latest", "answers": answers}
        return _Resp(200, body, text=_dumps(body))

    monkeypatch.setattr("irodori_client.typesafe.requests.post", fake_post)

    debug_dir = tmp_path / "dbg"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "output:\n  dir: ./out\ntypesafe:\n  api_key: test\n"
        f"debug:\n  dir: {debug_dir}\n",
        encoding="utf-8",
    )
    rc = main([
        "--config", str(cfg),
        "--debug",
        "mark",
        str(FIXTURES / "mini_novel.txt"),
        "-o", str(tmp_path / "out"),
    ])
    assert rc == 0

    runs = list(debug_dir.iterdir())
    assert len(runs) == 1
    run = runs[0]
    for name in (
        "000_meta.json", "001_request.json", "001_state.txt",
        "001_questions.pretty.json", "001_http.json", "001_response.json",
    ):
        assert (run / name).exists(), name

    request = json.loads((run / "001_request.json").read_text(encoding="utf-8"))
    assert set(request) == {"state", "model", "questions"}

    state_txt = (run / "001_state.txt").read_text(encoding="utf-8")
    assert "[本文]" in state_txt and "「おはよう」" in state_txt

    http = json.loads((run / "001_http.json").read_text(encoding="utf-8"))
    attempt = http["attempts"][0]
    assert attempt["request"]["method"] == "POST"
    assert attempt["request"]["url"].endswith("/v1/systemone")
    assert attempt["request"]["headers"]["Authorization"] == "Bearer <redacted>"
    assert "test" not in json.dumps(attempt["request"]["headers"])
    assert attempt["request"]["body_json"]["state"]
    assert attempt["response"]["status_code"] == 200
    assert "answers" in attempt["response"]["body_json"]

    meta = json.loads((run / "000_meta.json").read_text(encoding="utf-8"))
    assert meta["dialogue_lines"] == 4
