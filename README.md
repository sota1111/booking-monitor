# booking-monitor

予約サイトの空き状況を監視し、空きが見つかった場合に Discord で通知するシステムです。Cloud Scheduler と Cloud Run を組み合わせることで、低コストかつ安定した定期監視を実現します。

## アーキテクチャ

```
Cloud Scheduler (cron: 0 * * * *)
  └──POST /run──► Cloud Run (app.py)
                     ├──► 予約サイト確認 (Playwright / HTTP)
                     ├──► Firestore (前回結果・通知履歴)
                     └──► Discord Webhook (状態変化時のみ)
```

## 必要な環境

- Python 3.10 以上
- pip
- Docker（Cloud Run 使用時）
- GCP アカウント（Cloud Run 使用時）

## ローカル実行方法

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

### 3. 設定の準備
`.env.example` をコピーして `.env` を作成し、`DISCORD_WEBHOOK_URL` を設定します。
```bash
cp .env.example .env
```

`config.example.json` をコピーして `config.json` を作成し、監視対象を設定します。
```bash
cp config.example.json config.json
```

### 4. 実行
**定期実行モード:**
```bash
python main.py
```

**HTTP サーバーモード（Cloud Run 互換）:**
```bash
python app.py
```
※Firestore が設定されていない場合、ローカルの JSON ファイル（`logs/history.jsonl` など）に履歴を保存して動作します。

## 認証設定

このアプリは Firebase Authentication を使用したログイン認証が必要です。`.env` に以下の変数を設定してください。

### Firebase 設定
Firebase Console > プロジェクト設定 > アプリ から取得してください。

| 変数名 | 説明 |
|--------|------|
| FIREBASE_API_KEY | Firebase API キー |
| FIREBASE_AUTH_DOMAIN | Firebase 認証ドメイン |
| FIREBASE_PROJECT_ID | Firebase プロジェクト ID |
| FIREBASE_APP_ID | Firebase アプリ ID |

### ユーザー制御
| 変数名 | 説明 | 例 |
|--------|------|-----|
| ALLOWED_USER_EMAILS | ログインを許可するメールアドレス（カンマ区切り） | `your-email@example.com` |
| AUTH_SECRET | セッション署名キー（必ず変更してください） | `random-secret-string` |

### 動作確認方法

1. Firebase Console で「Email/Password」認証を有効にします。
2. ユーザーを作成し、そのメールアドレスを `ALLOWED_USER_EMAILS` に追加します。
3. `python app.py` でサーバーを起動（または `docker compose up`）
4. http://localhost:8080 にアクセス → ログイン画面にリダイレクトされる
5. Firebase で作成したメールアドレスとパスワードでログイン
6. ログアウトはステータス画面右上の「ログアウト」ボタンから

**注意**: Cloud Scheduler から呼び出される `POST /run` エンドポイントは認証不要です。


## Docker での実行方法

```bash
docker build -t booking-monitor .
docker run --env-file .env -p 8080:8080 -v $(pwd)/config.json:/app/config.json booking-monitor
```

別ターミナルで動作確認を行うには、以下のコマンドを実行します。
```bash
curl -X POST http://localhost:8080/run
```

## GCP 環境のセットアップ

### 6.1 Firestore のセットアップ
1. GCP コンソールで **Firestore** を選択。
2. **ネイティブ モード**でデータベースを作成。
3. データベース ID: `(default)` 推奨。
4. リージョン: `asia-northeast1` (東京) 推奨。
5. 無料枠: 1GiB ストレージ、50,000 読み取り/日、20,000 書き込み/日。

### 6.2 Cloud Run へのデプロイ
```bash
# デプロイスクリプトを使う方法（推奨）
GCP_PROJECT_ID=your-project-id \
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... \
bash scripts/deploy-cloudrun.sh
```
`--no-allow-unauthenticated` フラグにより、認証済みリクエスト（Cloud Scheduler 等）のみが許可されます。

### 6.3 Cloud Scheduler の設定
```bash
# サービスアカウント作成（Cloud Run 呼び出し用）
gcloud iam service-accounts create scheduler-sa \
  --display-name "Scheduler Service Account"

# Cloud Run 呼び出し権限を付与
gcloud run services add-iam-policy-binding booking-monitor \
  --region asia-northeast1 \
  --member serviceAccount:scheduler-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role roles/run.invoker

# Cloud Run の URL を取得（デプロイ出力等で確認）
CLOUD_RUN_URL=https://booking-monitor-XXXX-an.a.run.app

# Scheduler ジョブ作成（1時間に1回）
gcloud scheduler jobs create http booking-monitor-job \
  --location asia-northeast1 \
  --schedule "0 * * * *" \
  --time-zone "Asia/Tokyo" \
  --uri "${CLOUD_RUN_URL}/run" \
  --http-method POST \
  --oidc-service-account-email scheduler-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --oidc-token-audience "${CLOUD_RUN_URL}"
```

## Discord 通知の設定方法
1. Discord サーバーの「サーバー設定」→「連携サービス」→「Webhook」→「新しい Webhook を作成」。
2. Webhook URL をコピーして `DISCORD_WEBHOOK_URL` に設定。
3. 通知条件: 空き状況が「満席 → 空きあり」に変化したときのみ送信されます（重複通知なし）。

## 無料枠内で運用する前提条件

| サービス | 無料枠 | 想定使用量 |
|---------|-------|---------|
| Cloud Run | 180,000 vCPU 秒/月、360,000 GiB 秒/月 | 監視処理は数秒で完了 ✓ |
| Cloud Scheduler | 3 ジョブまで無料 | 1 ジョブ使用 ✓ |
| Firestore | 50,000 読み取り/日、20,000 書き込み/日、1GiB | 1 回の実行で数読み書き ✓ |
| Container Registry | 0.5GiB/月まで無料 | 定期的なクリーンアップを推奨 |

**Cloud Scheduler は 3 ジョブまで無料**のため、複数の監視対象は 1 つのジョブでまとめて実行することを推奨します（`config.json` に複数の `targets` を定義）。

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
- **ローカル:** `logs/booking_monitor.log`
- **Cloud Run:** `gcloud logging read "resource.type=cloud_run_revision"` または GCP コンソールの「ログ」タブ

## 注意事項
- 確認間隔は短すぎる値（60秒未満）を避けてください。
- 本システムは空き確認と通知のみを行います。予約の自動確定は行いません。
- 対象サイトの利用規約に従って使用してください。
