#!/usr/bin/env bash
set -euo pipefail

# ローカル gcloud CLI 認証による Cloud Run デプロイスクリプト
# (booking-monitor)
#
# 使い方:
#   cp .env.example .env && vi .env
#   source .env && bash scripts/deploy_local_gcp.sh

if [ -f .env ]; then set -a; source .env; set +a; fi

PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${GCP_REGION:-asia-northeast1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-booking-monitor}"
ARTIFACT_REPO="${ARTIFACT_REGISTRY_REPOSITORY:-booking-monitor-registry}"
IMAGE_VAR="${IMAGE_NAME:-booking-monitor}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${IMAGE_VAR}"

echo "== Cloud Run デプロイ: ${SERVICE_NAME} =="
echo "Project: ${PROJECT_ID} | Region: ${REGION}"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

gcloud artifacts repositories describe "${ARTIFACT_REPO}" \
  --project="${PROJECT_ID}" --location="${REGION}" &>/dev/null || \
gcloud artifacts repositories create "${ARTIFACT_REPO}" \
  --project="${PROJECT_ID}" --location="${REGION}" \
  --repository-format=docker \
  --description="Booking Monitor Docker images"

gcloud builds submit . \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}:latest" \
  --timeout=600s

# Secret Manager: 初回デプロイ前に以下を実行してください
# echo -n "value" | gcloud secrets create booking-monitor-auth-password --data-file=- --project=$PROJECT_ID
# echo -n "value" | gcloud secrets create booking-monitor-auth-secret-key --data-file=- --project=$PROJECT_ID
# echo -n "value" | gcloud secrets create booking-monitor-discord-webhook-url --data-file=- --project=$PROJECT_ID
# gcloud run services add-iam-policy-binding booking-monitor \
#   --member="serviceAccount:$(gcloud run services describe booking-monitor --region=$REGION --project=$PROJECT_ID --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || echo PROJECT_NUMBER-compute@developer.gserviceaccount.com)" \
#   --role="roles/secretmanager.secretAccessor" --region=$REGION --project=$PROJECT_ID

gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}:latest" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},LOG_LEVEL=${LOG_LEVEL:-INFO},PORT=8080" \
  --set-secrets="DISCORD_WEBHOOK_URL=booking-monitor-discord-webhook-url:latest,AUTH_PASSWORD=booking-monitor-auth-password:latest,AUTH_SECRET_KEY=booking-monitor-auth-secret-key:latest" \
  --memory=1Gi \
  --timeout=300 \
  --quiet

URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)')

echo "== デプロイ完了 =="
echo "Service URL: ${URL}"