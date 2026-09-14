# 設置手順（Kurage 申請書記入アシスト）

AIエージェント（Claude Code など）にこのフォルダごと渡せば、ここを読んで設置まで進められます。

## 何が要るか

| | 要るもの | 備考 |
|---|---|---|
| 必須 | Python 3.10 以上 | |
| 必須 | ポート1つ | 既定 18354。`KFILLOUT_PORT` で変更 |
| 任意 | Ollama（ローカルLLM） | 無くても動く。**空欄の項目名を見分ける精度が落ちるだけ** |
| 任意 | LibreOffice | 旧形式（.doc / .xls / .rtf / .odt / .ods）を扱うときだけ要る |

**外部のAIサービスは使いません。** ファイルも会社情報もこのサーバーの外へ出ません。

## 手順

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 18354
```

`http://localhost:18354/` を開いて、まず「よく使う情報」に会社名・所在地・代表者を入れてください。

### ローカルLLM（任意）

空欄が「何を書く欄か」を見分けるのに使います。**申請書の文章は作らせません。**

```bash
ollama pull gemma4:12b-it-qat
```

別のホストで動かしているときは環境変数で差し替えます。

```bash
export KFILLOUT_OLLAMA=http://192.168.0.10:11434
export KFILLOUT_MODEL=gemma4:12b-it-qat
```

gemma4 は思考型なので `"think": false` を送っています（外すと応答が空になります）。

### 旧形式（.doc / .xls）を扱う場合

```bash
sudo apt install -y --no-install-recommends libreoffice-writer libreoffice-calc
```

`.doc` → `.docx` に直して埋め、**`.doc` に戻して**返します。指定様式のまま出せるようにするためです。

### 常駐させる（systemd）

```ini
[Unit]
Description=Kurage shinseisho kinyu assist (kfillout) :18354
After=network-online.target

[Service]
WorkingDirectory=/path/to/kfillout
ExecStart=/path/to/kfillout/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 18354 --proxy-headers --forwarded-allow-ips=*
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

### レンタルサーバーから公開する（任意）

`php/kfillout.php` を置き、同じ場所に `kfillout_config.php` を作ります。

```php
<?php define("KFILLOUT_BACKEND", "http://あなたのサーバー:18354");
```

`https://example.com/kfillout.php/` で開けます。**ファイルのアップロードを中継するので、
PHP の `upload_max_filesize` と `post_max_size` を 20MB 以上**にしてください。

## MCP（チャットから使う）

```bash
claude mcp add kfillout -- /path/to/kfillout/.venv/bin/python /path/to/kfillout/kfillout_mcp.py
```

Codex は `~/.codex/config.toml` に:

```toml
[mcp_servers.kfillout]
command = "/path/to/kfillout/.venv/bin/python"
args = ["/path/to/kfillout/kfillout_mcp.py"]
```

## 動作確認

```bash
.venv/bin/python -m pytest tests/ -q      # 10件
curl http://localhost:18354/healthz
```

同梱の `samples/J-SHIS利用申請（参考例）.docx` で試せます。空欄5か所のうち、
申請日と会社名が自動で入り、残る3か所（サービス名）は**人が書く欄として残ります**。

## 大事な約束

- **AIに申請書の文章を作らせません。** 入る文字は「今日の日付」「保存した会社情報」
  「あなたが書いた値」の3つだけです
- **様式を変えません。** PDFへ変換せず、旧形式は元の形式へ戻します
- **画像PDFは埋めません。** 文字が入っていないので当て推量になり、申請書としては事故になります
- 出てきたファイルは**下書き**です。提出の前に必ず人が全体を確かめてください

## ライセンス

MIT。同梱のサンプル様式は防災科学技術研究所が公開している参考例です。
