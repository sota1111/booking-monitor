import os
import logging
from flask import Blueprint, jsonify, request
from booking_monitor.services.config_loader import load_active_config
from booking_monitor.services.history_factory import get_history
from booking_monitor.services.monitor_service import run_checks

logger = logging.getLogger(__name__)
monitor_bp = Blueprint("monitor", __name__)

# Global flag to ensure OIDC_AUDIENCE warning is logged only once
_oidc_audience_warning_logged = False

@monitor_bp.route("/run", methods=["POST"])
def run_monitor():
    # Cloud Scheduler からの OIDC トークン検証
    auth_header = request.headers.get("Authorization", "")
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
                    logger.warning("OIDC_AUDIENCE is not set. Audience verification is skipped (not recommended).")
                    _oidc_audience_warning_logged = True

            # OIDC トークンを検証 (Audience を指定)
            claims = google.oauth2.id_token.verify_oauth2_token(
                token, request_adapter, audience=oidc_audience
            )

            # 呼び出し元サービスアカウント email の検証 (設定されている場合のみ)
            scheduler_sa_email = os.getenv("SCHEDULER_SA_EMAIL")
            if scheduler_sa_email:
                if claims.get("email") != scheduler_sa_email or not claims.get("email_verified"):
                    logger.warning(f"Unauthorized service account: {claims.get('email')}")
                    return jsonify({"error": "Unauthorized"}), 401
        except Exception as e:
            logger.warning("OIDC token verification failed: %s", type(e).__name__)
            return jsonify({"error": "Unauthorized"}), 401
    elif os.getenv("RUN_API_KEY") and request.headers.get("X-API-KEY") == os.getenv("RUN_API_KEY"):
        # APIキーによる簡易認証（開発・テスト用）
        pass
    else:
        # 認証経路に該当しない場合はデフォルト拒否
        return jsonify({"error": "Unauthorized"}), 401

    try:
        config = load_active_config()
        history = get_history()
        results = run_checks(config, history)
        return jsonify({"status": "ok", "results": results}), 200

    except Exception as e:
        logger.error(f"Execution error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500
