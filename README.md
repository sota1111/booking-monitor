# booking-monitor

予約サイトの空き状況を定期的に監視し、空きが見つかったら Discord で通知するシステムです。

## 概要

- 指定した予約サイトを設定した間隔で自動確認
- 空きが検出されたら Discord Webhook で通知
- 重複通知を抑制（同じ空き枠への連続通知なし）
- エラー発生時も監視継続

## 必要な環境

- Python 3.10 以上
- pip

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/sota1111/booking-monitor.git
cd booking-monitor
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、必要な値を設定してください。

```bash
cp .env.example .env
# .env を編集して DISCORD_WEBHOOK_URL を設定
```

### 4. 設定ファイルの作成

`config.example.json` をコピーして `config.json` を作成し、監視対象を設定してください。

```bash
cp config.example.json config.json
# config.json を編集して監視対象を設定
```

## 実行

```bash
python main.py
```

## 設定ファイル（config.json）の説明

| フィールド | 説明 |
|-----------|------|
| `targets[].name` | 監視対象の名前 |
| `targets[].url` | 予約サイトの URL |
| `targets[].interval_seconds` | 確認間隔（秒）。デフォルト: 300 |
| `targets[].available_keywords` | 空きありと判定するキーワード |
| `targets[].unavailable_keywords` | 空きなしと判定するキーワード |
| `targets[].notify` | 通知の有効/無効 |
| `targets[].site_type` | サイト種別（`tablecheck` または `generic`） |
| `targets[].conditions.adults` | 大人の人数 |
| `targets[].conditions.children_under_3` | 3歳以下の子供の人数 |
| `targets[].conditions.days_of_week` | 対象曜日（例: `["Saturday", "Sunday"]`） |
| `targets[].conditions.time` | 対象時刻（例: `"15:00"`） |
| `notification.type` | 通知方法（現在は `discord` のみ） |
| `notification.webhook_url_env` | Discord Webhook URL の環境変数名 |

## ログの確認

ログは `logs/booking_monitor.log` に出力されます。標準出力にも同時に表示されます。

```bash
tail -f logs/booking_monitor.log
```

## 監視の停止

`Ctrl+C` でプロセスを終了してください。

## 注意事項

- 確認間隔は短すぎる値（60秒未満）の設定を避けてください
- 本システムは空き確認と通知のみを行います。予約の自動確定は行いません
- 対象サイトの利用規約に従って使用してください
