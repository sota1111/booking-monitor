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

echo "== Cloud Run デプロイ: ${SERVICE_NAME} =="
echo "Project: ${PROJECT_ID} | Region: ${REGION}"

# Cloud Build でビルド & プッシュ（ローカル Docker 不要）
gcloud builds submit . \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" \
  --timeout=600s

# Cloud Run へデプロイ
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL}" \
  --memory=1Gi \
  --timeout=300 \
  --quiet

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')

echo ""
echo "== デプロイ完了 =="
echo "Service URL: ${URL}"
