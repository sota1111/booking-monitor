import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from booking_monitor.services.config_loader import load_active_config
from booking_monitor.services.history_factory import get_history
from booking_monitor.services.monitor_service import run_checks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["monitor"])

# Global flag to ensure OIDC_AUDIENCE warning is logged only once
_oidc_audience_warning_logged = False

@router.post("/run", name="run_monitor")
async def run_monitor(request: Request):
    # 1. OIDC Bearer Token Verification
    auth_header = request.headers.get("Authorization", "")
    authorized = False

    if auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ")[1]
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token
            request_adapter = google.auth.transport.requests.Request()

            oidc_audience = os.getenv("OIDC_AUDIENCE")
            if not oidc_audience:
                global _oidc_audience_warning_logged
                if not _oidc_audience_warning_logged:
                    logger.warning(
                        "OIDC_AUDIENCE is not set. Audience verification is skipped."
                    )
                    _oidc_audience_warning_logged = True

            # OIDC トークンを検証 (Audience を指定)
            claims = google.oauth2.id_token.verify_oauth2_token(
                token, request_adapter, audience=oidc_audience
            )

            # 呼び出し元サービスアカウント email の検証 (設定されている場合のみ)
            scheduler_sa_email = os.getenv("SCHEDULER_SA_EMAIL")
            if scheduler_sa_email:
                if claims.get("email") == scheduler_sa_email and claims.get("email_verified"):
                    authorized = True
                else:
                    logger.warning(f"Unauthorized service account: {claims.get('email')}")
            else:
                authorized = True
        except Exception as e:
            logger.warning("OIDC token verification failed: %s", type(e).__name__)

    # 2. API Key Fallback
    if not authorized:
        run_api_key = os.getenv("RUN_API_KEY")
        if run_api_key and request.headers.get("X-API-KEY") == run_api_key:
            authorized = True

    # 3. Session User Fallback (New requirement)
    if not authorized:
        if request.session.get("user"):
            authorized = True

    if not authorized:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        config = load_active_config()
        history = get_history()
        results = await run_checks(config, history)
        return {"status": "ok", "results": results}

    except Exception as e:
        logger.error(f"Execution error: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
