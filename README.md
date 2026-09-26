# irodori-client

Python CLI for turning Japanese novels into per-line speech with a local
[Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server)
(OpenAI-compatible `/v1/audio/speech`).

It has two subcommands:

- `mark` — attribute each dialogue (`「...」`) / inner-thought (`（...）`) line to
  a character with [TypeSafe](https://docs.typesafe.ai) System One (Jev) and
  append the speaker label (`f1`, `m1`, ...) to the line.
- `run-marked` — synthesize only the speaker-marked lines, using each
  character's `voice` from the novel's `cast` block.

There is no external manifest file: everything is driven by the irodori metadata
block at the top of the novel.

Japanese version: [README.ja.md](README.ja.md). Keep both files in sync when
editing.

## Requirements

- Python 3.10 or newer.
- `TYPESAFE_API_KEY` in the environment for `mark` (not needed for
  `mark --init-header`).
- A running Irodori-TTS-Server reachable at `config.yaml`'s `tts.base_url`
  (default `http://localhost:8088`) for `run-marked`.
- `ffmpeg` on `PATH` (or set `concat.ffmpeg` in `config.yaml`) for
  `run-marked --concat`.

## Install

A virtual environment keeps the two dependencies isolated from the system
Python. It is optional for such a small CLI, but recommended.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

With [uv](https://docs.astral.sh/uv/) (optional, equivalent):

```bash
uv venv && uv pip install -r requirements.txt
```

Run every command from the repository root: the package is not installed, so
`python -m irodori_client` resolves it from the current directory.

## Configure

Edit `config.yaml`:

```yaml
tts:
  base_url: http://localhost:8088
  model: irodori-tts
  voice: "5"           # fallback voice (used when cast has no voice)
  response_format: mp3
  speed: 1.0
  api_key: null
  irodori: {}          # optional irodori-specific inference options

split:
  # Split a line into multiple TTS requests when it is longer than max_chars.
  # 0 = no client-side splitting (server-side chunking remains in effect).
  max_chars: 140
  # Boundary characters tried in priority order when splitting long lines.
  boundary_chars: "。！？!?…、\n"

concat:
  # ffmpeg executable used by `run-marked --concat` (override if not on PATH).
  ffmpeg: ffmpeg

output:
  dir: ./out
debug:
  enabled: false      # --debug enables this; --debug-dir overrides the path
  dir: ./debug
cleaning:
  symbols_remove: [♡, ♥, ❤, ♪, ～, …]
```

Global options (must appear **before** the subcommand):

```bash
python -m irodori_client --config path/to/config.yaml mark input/jev_test.txt -o out
python -m irodori_client --debug mark input/jev_test.txt -o out
```

## Use cases

| Case | Input | Steps |
| --- | --- | --- |
| (1) Plain novel | no irodori header | `mark --init-header` → hand-edit the cast → `mark` → `run-marked` |
| (2) eich novel (irodori + marked) | cast + markers | `run-marked` (optionally `mark` first to re-label) |
| (3) eich novel (irodori only) | cast, no markers | `mark` → `run-marked` |

```bash
# (1) Add an empty irodori header, then edit the cast block by hand.
python -m irodori_client mark input/plain_novel.txt -o out --init-header
$EDITOR out/plain_novel/plain_novel.txt
python -m irodori_client mark out/plain_novel/plain_novel.txt -o out

# (2) An eich novel that already has cast and markers.
python -m irodori_client run-marked input/eich_novel.txt -o out --speakers f1,f2

# (3) An eich novel with a cast block but no markers yet.
python -m irodori_client mark input/eich_novel.txt -o out
python -m irodori_client run-marked out/eich_novel/eich_novel.txt -o out
```

The `novel_id` is the input file name without the `.txt` extension (a trailing
`.marked` is stripped). All outputs go under `<out>/<novel_id>/`.

## Output layout

```
<out>/<novel_id>/<novel_id>.txt            # mark output (marked novel)
<out>/<novel_id>/<novel_id>.report.json    # mark report
<out>/<novel_id>/L<line>.<fmt>             # run-marked, single chunk
<out>/<novel_id>/L<line>_<split>.<fmt>     # run-marked, split line (_1, _2, ...)
<out>/<novel_id>/list.txt                  # run-marked --concat (ffmpeg list)
<out>/<novel_id>/<novel_id>.<fmt>          # run-marked --concat (joined audio)
```

* `<line>` is the novel line number, zero-padded to 4 digits (`L0027`).
* `<split>` is 1-based and has no zero padding (`_1`, `_2`, ...). It is only
  added when a line is split into more than one request.
* Lines without a marker are never synthesized.

## Novel metadata block (irodori format)

A novel starts with an HTML comment holding YAML metadata. It describes the
cast (`cast`), optional presets, and optional derived profiles. The client
scans for the first `<!-- ... -->` block that parses as YAML and contains a
`cast` key; other comments are skipped.

```html
<!--
format: irodori
version: 1

cast:
  f1: { voice: irodori_female_006, name: "アリス", gender: female, caption: "落ち着いた女性", description: "物語の主人公。冷静だが押しに弱い。" }
  m1: { voice: irodori_male_008, name: "ボブ", gender: male, caption: "低めの男性", description: "口数は少ないが面倒見がよい。" }

preset:
  angry: { emoji: 😠, speed: 1.05 }

profile:
  m1a: { base: m1, preset: [angry] }
-->
```

`mark --init-header` writes this template:

```
<!--
format: irodori
version: 1

cast:
  f1: { voice: "", name: "", gender: female, description: "通常シーン" }
  f2: { voice: "", name: "", gender: female, description: "エッチなシーン" }
  m1: { voice: "", name: "", gender: male, description: "" }
-->
```

### Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `format` | no | Informational; set to `irodori`. |
| `version` | no | Metadata schema version; currently `1`. |
| `cast` | **yes** | Map of speaker label → entry (see below). An empty `cast` is an error. |
| `preset` | no | Named presets (e.g. an emoji and speed). Parsed but not used yet. |
| `profile` | no | Derived characters, e.g. `{ base: m1, preset: [angry] }`. Parsed but not used yet. |

### `cast` entries

The key is the speaker label and must match `[fm]\d{1,2}` (for example `f1`,
`m2`, `M12`). Labels link the metadata, the line-end marker, and the per-line
voice.

| Entry field | Used by | Purpose |
| --- | --- | --- |
| `voice` | `run-marked` | Irodori voice identifier (e.g. `irodori_female_006`). Used per line. |
| `name` | `mark` | Character name, sent to Jev as a candidate. |
| `gender` | `mark` | `male` / `female` / etc. |
| `caption` | `mark` + `run-marked` | Jev criterion for `mark`; sent to Irodori as `irodori.caption` (voice/style) by `run-marked`. |
| `description` | `mark` | Longer description; the most useful field for attribution accuracy. Not sent to Irodori. |

An entry may also be a plain string, which is treated as `caption`:

```yaml
cast:
  f1: 落ち着いた女性
```

> YAML flow mappings need a space after the colon: write `caption: "..."`, not
> `caption:"..."` (the latter is parsed as a key literally named `caption:"..."`).

## How the metadata maps to irodori

The same label drives everything:

| Metadata | Marked line | `run-marked` |
| --- | --- | --- |
| `cast.<label>` key | suffix appended by `mark`: `「...」f1` | selects the speaker |
| `cast.<label>.voice` | — | TTS voice for that line |
| `cast.<label>.caption` | Jev `criteria` + state legend | `irodori.caption` (voice/style) |
| `name` / `gender` / `description` | Jev `criteria` + state legend | — |
| `preset` / `profile` | — | reserved for future emotion selection |

The line-end marker written by `mark` is exactly the form `run-marked`
recognizes:

```
^(?P<body>.*[）」\)])[ \t　]*(?P<label>[fmFM]\d{1,2})[ \t　]*$
```

> Line numbers use `content.split("\n")` (1-based; empty and trailing lines
> count). The metadata comment is part of the novel content, so its lines are
> counted too.

## Irodori-side preparation

For an app that generates novels (eich.jp v2), the client expects:

1. **The metadata block** as the first lines of the generated novel content
   (an HTML comment holding YAML with `format`/`version`/`cast`).
2. **Labels** matching the line-end markers (`m1,m2,…` for male characters,
   `f1,f2,…` otherwise). Labels are the shared key.
3. **`voice`** for each cast entry filled with the character's Irodori voice id
   (e.g. `irodori_female_006`).
4. **The descriptive fields** (`name`, `gender`, `caption`, `description`) from
   the character assets. They are not used for synthesis but greatly improve
   `mark`'s attribution.
5. **Marker lines** (`「...」f1`) if the novel is already labelled. If it is not,
   the `mark` command can add them.

The app can either ship novels already marked (case 2) or ship only the cast
block and let the client run `mark` (case 3).

## `mark`

Reads the `cast` metadata block, detects dialogue / inner-thought lines, asks
Jev who speaks each line, and appends the speaker label to the end of the line.
Narration is left untouched, and answers below the confidence threshold stay
unmarked. Re-running `mark` **replaces** existing markers, so it is safe on an
already marked novel.

```bash
export TYPESAFE_API_KEY=<your-api-key>
python -m irodori_client mark input/jev_test.txt -o out
```

Output:

```
out/jev_test/jev_test.txt          # marked novel, e.g. 「こんにちは」f1
out/jev_test/jev_test.report.json  # per-line label, confidence, status, probabilities
```

`--init-header` writes the empty template (with the original novel appended)
and exits without calling the API.

Flags:

```bash
--init-header              # prepend an empty irodori header and exit
--context-lines N          # context lines before/after each chunk (default 20)
--max-lines-per-request N  # dialogue lines per Jev request (default 40)
--min-confidence F         # answers below F stay unmarked (default 0.5)
--model / --base-url / --api-key-env / --timeout
--dry-run                  # parse cast and plan requests without calling the API
```

Behavior notes:

* Dialogue (`「...」`) and inner thoughts (`（...）`) are both attributed.
* Each question instructs Jev to read the surrounding narration (the numbered
  `[本文]` in the state) and tells it that when a character name appears in
  the narration, that is the author's note indicating who the line belongs to.
* When one line contains several fragments, a single label is appended at the
  line end.
* Lines whose body does not end with a closing bracket are counted in the
  report `not_ended_with_bracket` because the line-end marker will not match
  them.

## `run-marked`

Synthesizes only the speaker-marked lines. Lines without a marker are skipped.
Each line uses `cast.<label>.voice` and `cast.<label>.caption`:

* `voice` → the TTS voice for the line (falls back to `config.tts.voice`).
* `caption` → sent to Irodori as `irodori.caption` (voice/style description for
  caption-enabled Voice Design). If the cast entry has no `caption` or it is an
  empty string, no `irodori.caption` is sent. `description` is not used.

```bash
# All marked lines, each with its cast voice/caption.
python -m irodori_client run-marked out/jev_test/jev_test.txt -o out

# Only the female speakers (male voices not set up, etc.), and join the result.
python -m irodori_client run-marked out/jev_test/jev_test.txt -o out --speakers f1,f2 --concat
```

Flags:

```bash
--speakers f1,f2   # only these labels (comma/space separated, case-insensitive)
--voice NAME       # override every line with a single voice (captions still from cast)
--concat           # write list.txt and concatenate the segments into <novel_id>.<fmt>
--model / --speed / --base-url / --api-key
--skip-existing    # skip existing L*.mp3 files (idempotent)
```

### Concatenation (`--concat`)

`--concat` joins the same selection (marker lines + `--speakers`) into
`<out>/<novel_id>/<novel_id>.<fmt>` using `ffmpeg -f concat -c copy` (lossless
stream copy). It also writes `<out>/<novel_id>/list.txt` (ffmpeg concat demuxer
format) and keeps it, so the same join can be reproduced from the shell:

```bash
ffmpeg -y -f concat -safe 0 -i out/<novel_id>/list.txt -c copy -vn joined.mp3
```

Missing segments (e.g. a line that failed) are skipped with a warning. The
`ffmpeg` executable can be overridden with `concat.ffmpeg` in `config.yaml`.

## How splitting works

A marked line is split into one or more requests of at most `split.max_chars`
characters. Chunks break at a boundary character whenever possible: the
algorithm scans the first `split.max_chars`-character window of the remaining
text and splits at the last occurrence of the highest-priority boundary char
found (`。` > `！` > `？` > `!` > `?` > `…` > `、` > newline). If no boundary
character is present, the text is hard-cut at `split.max_chars`.

When `split.max_chars > 0`, the client also sends
`irodori.chunking_enabled: false` per request, so the server does not re-chunk
what the client already split.

## Debug mode (Jev requests)

When `debug.enabled` is true, or the global `--debug` flag is passed, every
Jev request and its response are written under `<debug.dir>/<timestamp>/`:

```
000_meta.json              # settings, cast, line counts
001_request.json           # logical payload: {state, model, questions}
001_state.txt              # the same state with real newlines (easy to read)
001_questions.pretty.json  # just the questions, pretty-printed
001_http.json              # full HTTP exchange(s): see below
001_response.json          # parsed JSON response
001_error.json             # only when the request fails
```

`001_http.json` contains every attempt (including retries) with the complete
HTTP information:

```json
{
  "attempts": [
    {
      "attempt": 1,
      "request": {
        "method": "POST",
        "url": "https://api.typesafe.ai/v1/systemone",
        "headers": { "...": "...", "Authorization": "Bearer <redacted>" },
        "body_text": "<raw body exactly as sent>",
        "body_json": { "state": "...", "model": "...", "questions": {} }
      },
      "response": {
        "status_code": 200,
        "reason": "OK",
        "headers": { "...": "..." },
        "body_text": "<raw response text>",
        "body_json": { "answers": {} },
        "elapsed_ms": 1234.5
      }
    }
  ]
}
```

* `--debug` enables debug mode; `--debug-dir PATH` overrides the directory
  (and enables it).
* Each run gets its own timestamped subdirectory, so runs never overwrite
  each other.
* The `Authorization` header is always replaced with `Bearer <redacted>`; the
  API key is never written to debug output.
* The `state` field is a single JSON-escaped string, so use `001_state.txt`
  to inspect the surrounding text that is sent to Jev.
* The default `./debug` is gitignored. Debug output is never sent anywhere;
  it is only for local inspection.

## Development / tests

```bash
pip install -r requirements-dev.txt
pytest
```

With uv, without installing anything persistently:

```bash
uv run --with-requirements requirements-dev.txt pytest
```

The suite is network-free: TTS and TypeSafe calls are mocked. Fixtures live in
`tests/fixtures/` and golden outputs in `tests/expected/`.

| Path | Purpose |
| --- | --- |
| `tests/fixtures/mini_novel.txt` | Cast block, dialogue, thought, multi-fragment and symbol-cleaning cases. |
| `tests/fixtures/mini_marked_cast.txt` | Cast block + marked lines (per-character voice). |
| `tests/fixtures/mini_marked.txt` | Marked lines without a cast block (fallback voice). |
| `tests/expected/` | Golden marked text and report. |

The large files under `input/` are manual/integration samples and are not used
by the test suite.
