# irodori-client

日本語小説を、ローカルの
[Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server)
（OpenAI 互換 `/v1/audio/speech`）でセリフ単位の音声にする Python CLI です。

サブコマンドは 2 つ:

- `mark` — [TypeSafe](https://docs.typesafe.ai) System One（Jev）で、各セリフ
  （`「...」`）/ 心の声（`（...）`）の話者を同定し、話者ラベル（`f1`, `m1` など）
  を行末に付与します。
- `run-marked` — 話者マーカー付きの行だけを、小説の `cast` の `voice` を使っ
  て話者ごとに音声合成します。

外部 manifest ファイルは使いません。すべて小説冒頭の irodori メタデータ
ブロックで駆動します。

English version: [README.md](README.md)。編集時は両ファイルを同期させて
ください。

## 動作要件

- Python 3.10 以上。
- `mark` には環境変数 `TYPESAFE_API_KEY`（`mark --init-header` では不要）。
- `run-marked` には `config.yaml` の `tts.base_url`（既定
  `http://localhost:8088`）で到達できる Irodori-TTS-Server。

## インストール

仮想環境を使うと、2 つの依存をシステムの Python から分離できます。小さな
CLI なので必須ではありませんが推奨します。

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

[uv](https://docs.astral.sh/uv/) を使う場合（任意・同等）:

```bash
uv venv && uv pip install -r requirements.txt
```

コマンドは必ずリポジトリのルートで実行してください（パッケージは未インストー
ルのため、`python -m irodori_client` はカレントディレクトリから解決されます）。

## 設定

`config.yaml` を編集します:

```yaml
tts:
  base_url: http://localhost:8088
  model: irodori-tts
  voice: "5"           # フォールバック voice（cast に voice が無い場合）
  response_format: mp3
  speed: 1.0
  api_key: null
  irodori: {}          # irodori 固有の推論オプション（任意）

split:
  # 行が max_chars を超えるとき、TTS リクエストを分割する。
  # 0 = クライアント分割なし（サーバ側の分割は有効なまま）。
  max_chars: 140
  # 分割時に優先する境界文字（優先順）。
  boundary_chars: "。！？!?…、\n"

output:
  dir: ./out
debug:
  enabled: false      # --debug で有効化、--debug-dir でパス上書き
  dir: ./debug
cleaning:
  symbols_remove: [♡, ♥, ❤, ♪, ～, …]
```

グローバルオプションはサブコマンドの**前**に置きます:

```bash
python -m irodori_client --config path/to/config.yaml mark input/jev_test.txt -o out
python -m irodori_client --debug mark input/jev_test.txt -o out
```

## 使い分け（3 ケース）

| ケース | 入力 | 手順 |
| --- | --- | --- |
| (1) 通常小説 | irodori ヘッダ無し | `mark --init-header` → cast を手修正 → `mark` → `run-marked` |
| (2) eich 小説（irodori + marked） | cast + マーカー | `run-marked`（必要なら `mark` で再付与） |
| (3) eich 小説（irodori のみ） | cast のみ | `mark` → `run-marked` |

```bash
# (1) 空の irodori ヘッダを付与し、cast ブロックを手で編集する。
python -m irodori_client mark input/plain_novel.txt -o out --init-header
$EDITOR out/plain_novel/plain_novel.txt
python -m irodori_client mark out/plain_novel/plain_novel.txt -o out

# (2) cast とマーカーが既にある eich 小説。
python -m irodori_client run-marked input/eich_novel.txt -o out --speakers f1,f2

# (3) cast はあるがマーカーがまだ無い eich 小説。
python -m irodori_client mark input/eich_novel.txt -o out
python -m irodori_client run-marked out/eich_novel/eich_novel.txt -o out
```

`novel_id` は入力ファイル名から `.txt` を除いたもの（末尾の `.marked` は
除去）です。出力はすべて `<out>/<novel_id>/` 配下に置かれます。

## 出力規則

```
<out>/<novel_id>/<novel_id>.txt            # mark の出力（マーカー付き小説）
<out>/<novel_id>/<novel_id>.report.json    # mark のレポート
<out>/<novel_id>/L<line>.mp3               # run-marked（分割なし）
<out>/<novel_id>/L<line>_<split>.mp3       # run-marked（分割あり _1, _2, ...）
```

* `<line>` は本文の行番号（4 桁ゼロ埋め。例 `L0027`）。
* `<split>` は 1 始まりでゼロ埋めなし（`_1`, `_2`, ...）。1 行が複数リクエ
  ストに分割されたときだけ付きます。
* マーカーの無い行は音声生成されません。

## 小説冒頭のメタデータ（irodori 形式）

小説は先頭に、YAML を格納した HTML コメントでメタデータを持ちます。
登場人物（`cast`）、任意のプリセット、任意の派生プロファイルを記述します。
クライアントは YAML として解釈でき、`cast` キーを持つ最初の
`<!-- ... -->` ブロックを探します。それ以外のコメントは無視します。

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

`mark --init-header` は次のテンプレートを付与します:

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

### フィールド

| フィールド | 必須 | 意味 |
| --- | --- | --- |
| `format` | 任意 | 情報用。`irodori` を設定。 |
| `version` | 任意 | スキーマ版。現在は `1`。 |
| `cast` | **必須** | 話者ラベル → エントリのマップ（下記）。空の `cast` はエラー。 |
| `preset` | 任意 | 名前付きプリセット（絵文字や速度など）。解析のみで未使用。 |
| `profile` | 任意 | 派生キャラ。例 `{ base: m1, preset: [angry] }`。解析のみで未使用。 |

### `cast` エントリ

キーは話者ラベルで、`[fm]\d{1,2}`（例 `f1`, `m2`, `M12`）に一致する必要が
あります。ラベルはメタデータ・行末マーカー・per-line の voice を結ぶ鍵です。

| エントリ | 使用側 | 用途 |
| --- | --- | --- |
| `voice` | `run-marked` | Irodori のボイス識別子（例 `irodori_female_006`）。行ごとに使用。 |
| `name` | `mark` | キャラクタ名。Jev の候補として送信。 |
| `gender` | `mark` | `male` / `female` など。 |
| `caption` | `mark` | 短い一行説明。 |
| `description` | `mark` | 長い説明。話者同定の精度に最も効きます。 |

エントリは単なる文字列でもよく、その場合は `caption` として扱われます:

```yaml
cast:
  f1: 落ち着いた女性
```

## メタデータが irodori にどう反映されるか

同じラベルがすべてを駆動します:

| メタデータ | マーカー付き行 | `run-marked` |
| --- | --- | --- |
| `cast.<label>` キー | `mark` が付与: `「...」f1` | 話者の選択 |
| `cast.<label>.voice` | — | その行の TTS voice |
| `name` / `gender` / `caption` / `description` | Jev の `criteria` と state の凡例 | — |
| `preset` / `profile` | — | 将来の感情選択用に予約 |

`mark` が書き込む行末マーカーは、`run-marked` が認識する形そのものです:

```
^(?P<body>.*[）」\)])[ \t　]*(?P<label>[fmFM]\d{1,2})[ \t　]*$
```

> 行番号は `content.split("\n")`（1 始まり。空行・末尾空行も数える）です。
> メタデータコメントも本文の一部なので、その行も数えられます。

## irodori 側の準備

アプリ（eich.jp v2）が小説を生成する場合、クライアントは次を期待します:

1. **メタデータブロック**を生成する小説 content の先頭行に置く（`format` /
   `version` / `cast` を持つ YAML の HTML コメント）。
2. **ラベル**を行末マーカーと一致させる（男性キャラは `m1,m2,…`、それ以外は
   `f1,f2,…`）。ラベルが共有の鍵です。
3. 各 cast エントリの **`voice`** に、キャラクタの Irodori voice id
   （例 `irodori_female_006`）を設定する。
4. **説明フィールド**（`name` / `gender` / `caption` / `description`）を
   キャラクタ資産から取り込む。音声合成には使いませんが、`mark` の同定精度を
   大きく改善します。
5. 既にラベル付け済みなら**マーカー行**（`「...」f1`）を持たせる。無ければ
   `mark` コマンドで付与できる。

アプリは、マーカー付きで出荷する（ケース 2）か、cast ブロックだけ出荷して
クライアントに `mark` させる（ケース 3）かを選べます。

## `mark`

`cast` メタデータブロックを読み、セリフ/心の声の行を検出し、Jev に各行の
話者を問い合わせて、話者ラベルを行末に付与します。地の文はそのまま残し、
確信度が閾値未満の回答は未マーカーにします。再実行すると**既存のマーカーを
上書き**するため、既にマーカー付きの小説でも安全に使えます。

```bash
export TYPESAFE_API_KEY=<your-api-key>
python -m irodori_client mark input/jev_test.txt -o out
```

出力:

```
out/jev_test/jev_test.txt          # マーカー付き小説 例: 「こんにちは」f1
out/jev_test/jev_test.report.json  # 行ごとのラベル・確信度・status・確率
```

`--init-header` は空のテンプレート（元の小説を後ろに連結）を書き出して終了
します。API は呼びません。

フラグ:

```bash
--init-header              # 空の irodori ヘッダを付与して終了
--context-lines N          # 各チャンク前後の文脈行数（既定 20）
--max-lines-per-request N  # 1 Jev リクエストあたりのセリフ行数（既定 40）
--min-confidence F         # F 未満の回答は未マーカー（既定 0.5）
--model / --base-url / --api-key-env / --timeout
--dry-run                  # API を呼ばず cast を解析しリクエストを計画
```

挙動の注意:

* セリフ（`「...」`）と心の声（`（...）`）の両方を同定対象にします。
* 各質問は、セリフ行だけでなく前後の地の文（state の番号付き `[本文]`）を
  読んで判定するよう Jev に指示します。地の文にキャラクタ名が出る場合は、
  作者が誰のセリフか補足したものとして扱わせます。
* 1 行に複数の断片がある場合も、ラベルは行末に 1 つだけ付与します。
* 本文が閉じ括弧で終わらない行は、行末マーカーが一致しないため、レポートの
  `not_ended_with_bracket` に計上されます。

## `run-marked`

話者マーカー付きの行だけを音声合成します。マーカーの無い行はスキップし、
各行は `cast.<label>.voice` の voice を使います（cast に voice が無ければ
`config.tts.voice` にフォールバック）。

```bash
# マーカー付き全行を、それぞれの cast voice で。
python -m irodori_client run-marked out/jev_test/jev_test.txt -o out

# 女性話者のみ（男性 voice を未セットアップの場合など）。
python -m irodori_client run-marked out/jev_test/jev_test.txt -o out --speakers f1,f2
```

フラグ:

```bash
--speakers f1,f2   # これらのラベルのみ（カンマ/空白区切り、大小文字無視）
--voice NAME       # 全行を単一 voice で上書き
--model / --speed / --base-url / --api-key
--skip-existing    # 既存の L*.mp3 をスキップ（冪等）
```

## 分割（チャンキング）の仕組み

マーカー付きの行は、最大 `split.max_chars` 文字の 1 つ以上のリクエストに
分割されます。境界文字があればそこで分割します。アルゴリズムは残りテキスト
の先頭 `split.max_chars` 文字の窓を走査し、見つかった最も優先度の高い境界
文字の最後の位置で分割します（`。` > `！` > `？` > `!` > `?` > `…` > `、`
> 改行）。窓内に境界文字が無ければ `split.max_chars` で強制分割します。

`split.max_chars > 0` のとき、クライアントはリクエストごとに
`irodori.chunking_enabled: false` も送るので、サーバ側で二重に分割されません。

## デバッグモード（Jev リクエスト）

`debug.enabled` が true、またはグローバルの `--debug` を指定すると、Jev の
リクエストと応答をすべて `<debug.dir>/<timestamp>/` 配下へ保存します:

```
000_meta.json              # 設定・cast・行数
001_request.json           # 論理ペイロード: {state, model, questions}
001_state.txt              # 同じ state を実改行で出力（読みやすい）
001_questions.pretty.json  # questions のみ整形
001_http.json              # HTTP の全情報（下記）
001_response.json          # パース済みの応答
001_error.json             # 失敗時のみ
```

`001_http.json` には全試行（リトライ含む）の HTTP 情報が入ります:

```json
{
  "attempts": [
    {
      "attempt": 1,
      "request": {
        "method": "POST",
        "url": "https://api.typesafe.ai/v1/systemone",
        "headers": { "...": "...", "Authorization": "Bearer <redacted>" },
        "body_text": "実際に送信された生ボディ",
        "body_json": { "state": "...", "model": "...", "questions": {} }
      },
      "response": {
        "status_code": 200,
        "reason": "OK",
        "headers": { "...": "..." },
        "body_text": "生の応答テキスト",
        "body_json": { "answers": {} },
        "elapsed_ms": 1234.5
      }
    }
  ]
}
```

* `--debug` で有効化、`--debug-dir PATH` でディレクトリを上書き（同時に有効化）。
* 実行ごとにタイムスタンプ付きサブディレクトリを作るため、過去の出力を
  上書きしません。
* `Authorization` ヘッダは常に `Bearer <redacted>` に置換され、API キーは
  デバッグ出力に書かれません。
* `state` は JSON エスケープされた1行の文字列なので、Jev に送っている前後
  の文章は `001_state.txt` を見てください。
* 既定の `./debug` は gitignore 済み。デバッグ出力は送信されず、ローカル
  確認専用です。

## 開発 / テスト

```bash
pip install -r requirements-dev.txt
pytest
```

uv を使い、恒久的にインストールせずに実行する場合:

```bash
uv run --with-requirements requirements-dev.txt pytest
```

テストはネットワークを使いません（TTS と TypeSafe の呼び出しはモック）。
フィクスチャは `tests/fixtures/`、期待出力（golden）は `tests/expected/`。

| パス | 目的 |
| --- | --- |
| `tests/fixtures/mini_novel.txt` | cast ブロック、セリフ、心の声、複数断片、記号除去。 |
| `tests/fixtures/mini_marked_cast.txt` | cast ブロック + マーカー付き行（per-character voice）。 |
| `tests/fixtures/mini_marked.txt` | cast 無しのマーカー付き行（フォールバック voice）。 |
| `tests/expected/` | マーカー付きテキストとレポートの golden。 |

`input/` 配下の大きなファイルは手動/結合テスト用のサンプルで、テスト
スイートでは使用しません。
