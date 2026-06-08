import os
import logging
from flask import Flask, jsonify
from booking_monitor.config import load_config
from booking_monitor.checker import check_target
from booking_monitor.history import History
from booking_monitor.notifier import Notifier

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_history():
    """Returns FirestoreHistory if configured, else local History."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        try:
            from booking_monitor.firestore_history import FirestoreHistory
            return FirestoreHistory()
        except Exception as e:
            logger.warning(f"Firestore unavailable, falling back to local history: {e}")
    return History()

@app.route("/run", methods=["POST"])
def run_monitor():
    try:
        config_path = os.getenv("CONFIG_PATH", "config.json")
        if not os.path.exists(config_path):
            # Fallback to example if config.json doesn't exist for easier testing/dev
            if os.path.exists("config.example.json"):
                config_path = "config.example.json"
        
        config = load_config(config_path)
        history = get_history()
        notifier = Notifier(config.notification)
        
        results = []
        for target in config.targets:
            try:
                available, summary = check_target(target)
                last_state = history.get_last_state(target.name)
                
                was_available = last_state.get("available", False) if last_state else False
                was_notified = last_state.get("notified", False) if last_state else False
                
                state_changed = available and not was_available
                notified_this_turn = False
                
                is_notified = was_notified
                if available:
                    if state_changed:
                        if target.notify:
                            notifier.send(target, summary)
                            is_notified = True
                            notified_this_turn = True
                else:
                    is_notified = False
                
                history.record(target.name, target.url, available, is_notified)
                
                results.append({
                    "target": target.name,
                    "available": available,
                    "summary": summary,
                    "notified": notified_this_turn or (available and was_notified),
                    "state_changed": state_changed
                })
            except Exception as e:
                logger.error(f"Error checking target {target.name}: {e}")
                history.record(target.name, target.url, False, False, error=str(e))
                results.append({
                    "target": target.name,
                    "available": False,
                    "summary": f"Error: {str(e)}",
                    "notified": False,
                    "state_changed": False
                })
        
        return jsonify({"status": "ok", "results": results}), 200
        
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
