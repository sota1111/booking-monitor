#!/usr/bin/env bash
set -euo pipefail

# Cloud Run デプロイスクリプト (booking-monitor)
# 使い方:
#   GCP_PROJECT_ID=your-project-id \
#   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... \
#   bash scripts/deploy-cloudrun.sh

PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${REGION:-asia-northeast1}"
SERVICE_NAME="booking-monitor"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:?DISCORD_WEBHOOK_URL is required}"
# 案1: server-side email/password auth needs the Firebase Web API key server-side.
FIREBASE_API_KEY="${FIREBASE_API_KEY:?FIREBASE_API_KEY is required}"
ALLOWED_USER_EMAILS="${ALLOWED_USER_EMAILS:?ALLOWED_USER_EMAILS is required}"
AUTH_SECRET="${AUTH_SECRET:?AUTH_SECRET is required}"

echo "== Cloud Run デプロイ: ${SERVICE_NAME} =="
echo "Project: ${PROJECT_ID} | Region: ${REGION}"

# Cloud Build でビルド & プッシュ（ローカル Docker 不要）
gcloud builds submit . \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" \
  --timeout=600s

# Cloud Run へデプロイ
# 案1: アプリ側の自前ログイン(セッション認証)で保護するため、Cloud Run サービス自体は
# 未認証アクセスを許可し、ログイン画面に到達できるようにする。各ルートはセッションで保護される。
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL},FIREBASE_API_KEY=${FIREBASE_API_KEY},ALLOWED_USER_EMAILS=${ALLOWED_USER_EMAILS},AUTH_SECRET=${AUTH_SECRET}" \
  --memory=1Gi \
  --timeout=300 \
  --quiet

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')

echo ""
echo "== デプロイ完了 =="
echo "Service URL: ${URL}"
