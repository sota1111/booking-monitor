# booking-monitor

予約サイトの空き状況を監視し、空きが見つかった場合に Discord で通知するシステムです。Cloud Scheduler と Cloud Run を組み合わせることで、低コストかつ安定した定期監視を実現します。

## アーキテクチャ

```
Cloud Scheduler (cron: 0 * * * *)
  └──POST /run──► Cloud Run (FastAPI/uvicorn)
                     ├──► 予約サイト確認 (Playwright / HTTPX)
                     ├──► Firestore または ローカル JSONL
                     │       ├── monitoring_results / history.jsonl（最新状態）
                     │       ├── check_history（時系列履歴）
                     │       └── notification_history（通知履歴）
                     └──► Discord Webhook（状態変化時のみ）

ブラウザ (ログイン後)
  └──GET /──────► ダッシュボード（監視一覧・状態・手動実行）
  └──GET /calendar──► カレンダー概観（範囲監視の日付×時刻スロット）
  └──GET /history──► 監視履歴
  └──GET /notification-history──► 通知履歴
  └──GET /config──► 設定確認
```

## 必要な環境

- Python 3.12 以上
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

**HTTP サーバーモード（FastAPI）:**
```bash
uvicorn app:app --reload --port 8080
# または
python app.py
```
※Firestore が設定されていない場合、ローカルの JSON ファイル（`logs/history.jsonl` など）に履歴を保存して動作します。

## ログイン必須の監視対象（案B: 手動セッション投入）

監視対象の予約サイトがログイン必須（例: Google SSO の TableCheck）の場合、未ログインのままだとログイン画面に飛ばされて予約状況を判定できません。Google SSO は自動ログイン（headless でのID/PW投入）を意図的にブロックするため、本アプリでは **手動でエクスポートしたログインセッション（Playwright `storage_state`）を注入する方式（案B）** に対応しています。Google のログイン処理自体は自動化しません。

### 仕組み
- 人が普段のブラウザで対象サイトに一度ログインし、`storage_state`（cookie + localStorage の JSON）をエクスポートします。
- その JSON を環境変数（Secret Manager 推奨）に格納し、対象の `session_state_env` にその**環境変数名**を指定します。
- 各チェックは `browser.new_context(storage_state=...)` で認証済みコンテキストを再現して巡回します。保存されるのは対象サイトのセッション cookie のみで、Google のパスワードや認証情報は保存しません。
- `session_state_env` が未設定の対象は従来どおり未認証で動作します（後方互換）。

### セットアップ手順
1. 対象サイトに手動ログイン後、`storage_state` をエクスポートします。
   ```python
   # Playwright で対象サイトにログイン後:
   context.storage_state(path="state.json")
   ```
   （Cookie-Editor 等のブラウザ拡張で対象ドメインの cookie を JSON エクスポートしても可）
2. エクスポートした JSON を環境変数 / Secret に登録します（例: `BOOKING_SESSION_STATE`）。
   ```bash
   # ローカル（.env）
   BOOKING_SESSION_STATE='{"cookies":[...],"origins":[...]}'

   # Cloud Run（Secret Manager）
   gcloud secrets create booking-session-state --data-file=state.json
   ```
3. `config.json` の対象に `session_state_env` を追加します。
   ```json
   "session_state_env": "BOOKING_SESSION_STATE"
   ```
4. monitor を再起動 / 再デプロイして新しいセッションを読み込ませます。

### セッション失効時
cookie/サーバ側セッションには有効期限があり（サイト依存で数日〜数週間）、失効すると未ログイン状態に戻ります。失効を検知すると（認証チェックがログイン画面へリダイレクトされると）、monitor は **Discord（既存の通知チャネル）に再エクスポート依頼を通知**し、その対象の監視を一時的に認証エラーとして記録します。通知を受けたら手順1〜4を再実行してセッションを更新してください。通知は失効ごとに1回だけ送信されます（毎チェックでは送りません）。

## 認証設定

このアプリは Firebase Authentication を使用したログイン認証が必要です。`.env` に以下の変数を設定してください。

### Firebase 設定
Firebase Console > プロジェクト設定 > アプリ から取得してください。

| 変数名 | 説明 |
|--------|------|
| FIREBASE_WEB_API_KEY | Firebase Web API キー（サーバサイドREST認証用・優先）。未設定時は `FIREBASE_API_KEY` にフォールバック |
| FIREBASE_API_KEY | Firebase API キー（`FIREBASE_WEB_API_KEY` 未設定時のフォールバック） |

### ユーザー制御
| 変数名 | 説明 | 例 |
|--------|------|-----|
| ALLOWED_USER_EMAILS | ログインを許可するメールアドレス（カンマ区切り） | `your-email@example.com` |
| AUTH_SECRET | セッション署名キー（必ず変更してください） | `random-secret-string` |

### 動作確認方法

1. Firebase Console で「Email/Password」認証を有効にします。
2. ユーザーを作成し、そのメールアドレスを `ALLOWED_USER_EMAILS` に追加します。
3. `uvicorn app:app` でサーバーを起動
4. http://localhost:8080 にアクセス → ログイン画面にリダイレクトされる
5. Firebase で作成したメールアドレスとパスワードでログイン
6. ログアウトはステータス画面右上の「ログアウト」ボタンから

### 定期実行用認証 (`POST /run`)

Cloud Scheduler からの呼び出しには OIDC 認証を使用します。以下の環境変数を設定することでセキュリティを強化できます。

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `OIDC_AUDIENCE` | トークンの期待 Audience。Cloud Run のサービス URL を設定します。 | `https://booking-monitor-xxxx.run.app` |
| `SCHEDULER_SA_EMAIL` | 呼び出しを許可するサービスアカウント Email（任意）。 | `scheduler-sa@project.iam.gserviceaccount.com` |
| `RUN_API_KEY` | 開発・テスト用の API キー（`X-API-KEY` ヘッダー）。 | `your-secret-key` |

**注意**: `OIDC_AUDIENCE` を設定した場合、呼び出し元の Audience 設定と一致しないと `401 Unauthorized` になります。
また、**ログイン済みのブラウザセッションがある場合も `/run` へのアクセスが許可されます**（ダッシュボードの手動実行ボタン用）。


## Web 画面一覧

ログイン後、以下の画面を利用できます。

| パス | 画面名 | 説明 |
|------|--------|------|
| `/` | ダッシュボード | 監視対象数・空きあり件数・最終チェック日時などのサマリーと、監視対象一覧を表示。手動実行ボタンも設置。 |
| `/calendar` | カレンダー概観 | 範囲監視（日付 × 時刻）の各スロットの空き/満席/不明を、カレンダー形式で概観表示します。 |
| `/history` | 監視履歴 | チェックごとの日時・結果・状態変化・エラー概要を時系列で確認できます。 |
| `/notification-history` | 通知履歴 | Discord 通知の送信日時・対象店舗・成功/失敗/スキップを表示。Webhook URL などの秘密情報は表示されません。 |
| `/config` | 設定確認 | config.json の監視条件（キーワード・チェック間隔・人数条件など）を画面で確認できます。秘密情報は表示されません。 |

### ダッシュボード（`/`）

- 上部に監視対象数・通知有効数・空きあり件数・満席件数・取得失敗件数・最終チェック日時・最終通知日時を表示
- 監視対象一覧: 店舗名（予約 URL リンク）・サイト種別・対象曜日と時刻・大人/子ども人数・通知 ON/OFF・状態バッジ・最終確認日時
- 状態バッジ:
  - 🟢 **空きあり** / **空きあり 通知済** — 予約可能な枠が見つかっている
  - ⬜ **満席** — 現在予約不可
  - 🔵 **未確認** — まだチェックが実行されていない
  - 🔴 **取得失敗** — チェック中にエラーが発生
- 手動実行ボタン: ボタン1つでチェックを即時実行。実行中は二重押下を防止し、完了後に結果（空きあり件数）を表示します。

### 監視履歴（`/history`）

- チェック日時（JST）・対象店舗名・空きあり/満席/取得失敗の結果・状態変化の有無・通知有無・サマリー・エラー概要を表示
- 店舗名でリアルタイム絞り込みが可能
- 最新の 200 件を表示（ローカル: `logs/check_history.jsonl` / Firestore: `check_history` コレクション）

### 通知履歴（`/notification-history`）

- Discord 通知の送信日時・対象店舗・送信成功/失敗/スキップの状態を確認できます
- 重複通知を防いだ場合は「通知スキップ」と表示します
- Webhook URL などの秘密情報は表示されません

### 設定確認（`/config`）

- config.json の全監視対象の設定内容を一覧表示します
- 空きありキーワード・満席キーワード・チェック間隔・人数条件・通知設定を確認できます
- チェック間隔（`interval_seconds`）が 60 秒未満の場合、画面上に警告を表示します
- TableCheck サイトと汎用 HTTP サイトの違いが分かるようにラベル表示します
- Webhook URL などの秘密情報（環境変数の値）は表示されません（環境変数名のみ表示）

## データ保存先（ローカル vs Firestore）

| 保存先 | 条件 | 保存ファイル/コレクション |
|--------|------|--------------------------|
| ローカル JSONL | `GOOGLE_CLOUD_PROJECT` 環境変数が未設定 | `logs/history.jsonl`（最新状態）<br>`logs/check_history.jsonl`（時系列履歴）<br>`logs/notification_history.jsonl`（通知履歴） |
| Firestore | `GOOGLE_CLOUD_PROJECT` 環境変数を設定済み | `monitoring_results`（最新状態）<br>`check_history`（時系列履歴）<br>`notification_history`（通知履歴） |

ローカルモードは Firestore なしで動作確認できます。`GOOGLE_CLOUD_PROJECT` を設定すると自動的に Firestore を使用します。
接続失敗時は自動的にローカル JSONL にフォールバックします。

## Docker での実行方法

```bash
docker build -t booking-monitor .
docker run --env-file .env -p 8080:8080 -v $(pwd)/logs:/app/logs -v $(pwd)/config.json:/app/config.json booking-monitor
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
### GCP Secret Manager セットアップ (Cloud Run本番デプロイ時)

Cloud Run へのデプロイ前に、以下の機密情報をSecret Managerに登録してください。

```bash
# Secret の作成
echo -n "パスワード" | gcloud secrets create booking-monitor-auth-password --data-file=- --project=YOUR_PROJECT_ID
echo -n "秘密鍵" | gcloud secrets create booking-monitor-auth-secret-key --data-file=- --project=YOUR_PROJECT_ID
echo -n "Webhook URL" | gcloud secrets create booking-monitor-discord-webhook-url --data-file=- --project=YOUR_PROJECT_ID

# Cloud Run サービスアカウントに Secret Manager アクセス権を付与
# (デプロイ後、またはデフォルトのコンピュートSAに付与)
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

ローカル開発では `.env` ファイルに値を直接設定してください。

```bash
# デプロイスクリプトを使う方法（推奨）
GCP_PROJECT_ID=your-project-id \
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... \
bash scripts/deploy-cloudrun.sh
```
`--allow-unauthenticated` フラグにより、未認証アクセスを許可し、各ルートはアプリケーション側のセッション（ログイン画面）で保護されます。

### 6.2.1 GitHub Actions による自動デプロイ (CI/CD)

`.github/workflows/deploy-cloudrun.yml` により、GitHub Actions から Cloud Run へ自動デプロイできます。

- **トリガー**: `main` ブランチへの push（手動実行用に `workflow_dispatch` も対応）
- **認証方式**: Workload Identity Federation（JSON キーは使用しない）
- **権限**: `permissions: contents: read` / `id-token: write`
- **処理**: Docker build → Artifact Registry push → Cloud Run deploy
- コンテナは **ポート 8080**（`$PORT`）で listen するため、追加のポート設定は不要

Settings → Secrets and variables → Actions で以下の **必須 Secret（10件）** を設定してください:

| Secret 名 | 説明 |
|---|---|
| `GCP_PROJECT_ID` | GCP プロジェクト ID |
| `GCP_REGION` | Cloud Run / Artifact Registry のリージョン（例: `asia-northeast1`） |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Federation プロバイダのリソース名 |
| `GCP_SERVICE_ACCOUNT` | デプロイ用サービスアカウントのメールアドレス |
| `ARTIFACT_REGISTRY_REPOSITORY` | Artifact Registry リポジトリ名 |
| `CLOUD_RUN_SERVICE` | Cloud Run サービス名（`booking-monitor`） |
| `FIREBASE_API_KEY` | Firebase API キー |
| `ALLOWED_USER_EMAILS` | ログインを許可するメールアドレス（カンマ区切り） |
| `AUTH_SECRET` | セッション署名用シークレット |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL |

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
| `targets[].site_type` | サイト種別（`tablecheck` または `generic`）。新しいサイトの追加方法は [docs/adding-a-site.md](docs/adding-a-site.md) を参照 |
| `targets[].conditions.adults` | 大人の人数 |
| `targets[].conditions.children_under_3` | 3歳以下の子供の人数 |
| `targets[].conditions.days_of_week` | 対象曜日（例: `["Saturday", "Sunday"]`）。`date_range` と併用すると範囲内の対象曜日のみに絞り込む |
| `targets[].conditions.time` | 対象時刻（例: `"15:00"`）。`time_range` 未指定時のフォールバック |
| `targets[].conditions.date_range` | 日付範囲。`{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}`（範囲監視。任意） |
| `targets[].conditions.time_range` | 時刻範囲。`{"start": "HH:MM", "end": "HH:MM", "step_minutes": 15}`（範囲監視。任意） |
| `notification.type` | 通知方法（現在は `discord` のみ）。`channels` が空のときに使う従来の単一通知先 |
| `notification.webhook_url_env` | Discord Webhook URL の環境変数名（従来の単一通知先用） |
| `notification.channels` | 複数通知先。`[{ "type", "webhook_url_env", "enabled" }]`。非空のときは `enabled` な全チャネルへ送信。空なら従来の `type`/`webhook_url_env` を使用（後方互換） |
| `notification.snooze_until` | 通知の一時停止（スヌーズ）。ISO 8601 UTC 時刻。現在時刻がこの時刻より前の間は通知を抑制。`null` または過去時刻なら有効 |

### 範囲監視（日付 × 時刻）

`conditions` に `date_range` と `time_range` を指定すると、その範囲を `step_minutes`（既定15分）
刻みで展開した各スロットの空き/満席を個別に取得します（AND 検索）。

- ダッシュボードに「日付 × 時刻」のグリッドを表示し、各スロットが空き（○）／満席（×）／不明（-）かを一覧できます。
- 通知は「範囲内のいずれかのスロットに空きが出た」タイミングで送信されます。
- 範囲監視は `tablecheck` 種別が対象です（`generic` はキーワード判定のみでスロット別取得は行いません）。
- `date_range`/`time_range` を指定しない既存の設定はそのまま単一状態として動作します（後方互換）。

> 注: 実カレンダーのスロット別空き状況の取得は対象サイトの DOM 構造に依存します。
> ライブ環境での挙動は実サイトでの確認を推奨します。

## ログの確認
- **ローカル:** `logs/booking_monitor.log`
- **Cloud Run:** `gcloud logging read "resource.type=cloud_run_revision"` または GCP コンソールの「ログ」タブ

## 注意事項
- 確認間隔は短すぎる値（60秒未満）を避けてください。
- 本システムは空き確認と通知のみを行います。予約の自動確定は行いません。
- 対象サイトの利用規約に従って使用してください。
