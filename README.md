# Cloud Tune

空の写真と感情ラベルから、似た空に紐づいた YouTube Music リンクを推薦するハッカソン向けWebアプリです。

音楽そのものは解析せず、過去に人が登録した「空の写真 + YouTube Musicリンク」の対応をたどります。

## 構成

```text
app/                    # フロントエンド静的ファイル
  index.html
  styles.css
  app.js
  mood_meter.png
  cloud_tune_logo.png

backend/cloud_tune/      # FastAPIバックエンド
  main.py
  features.py
  recommender.py
  db.py

data/                    # ローカル実行時のDB/画像置き場
```

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CLOUD_TUNE_WORKSPACE=(Get-Location).Path
$env:PYTHONPATH="$((Get-Location).Path)\backend"
uvicorn cloud_tune.main:app --host 0.0.0.0 --port 8000
```

起動後、ブラウザで以下を開きます。

```text
http://localhost:8000/
```

## 注意

- `data/*.sqlite3`、アップロード画像、取り込み済み写真はGit管理しません。
- YouTubeのメタデータは保存せず、リンクだけを扱います。
- 初期データを使う場合は、別途 `data/photos/` とSQLite DBを用意してください。
