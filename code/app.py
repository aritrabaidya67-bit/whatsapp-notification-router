"""
Production HTTP Microservice API for Multimodal WhatsApp Notification Router.
Provides REST API endpoints for real-time notification routing, batch routing,
user feedback ingestion, and health metrics.
Uses Python standard library http.server with optional FastAPI / Uvicorn support.
"""
import sys
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataStore
from classifier import classify_message
from validator import validate_predictions
from feedback_loop import AdaptivePersonalizationEngine

# Global instances
DATA_STORE = None
FEEDBACK_ENGINE = None


def get_datastore():
    global DATA_STORE, FEEDBACK_ENGINE
    if DATA_STORE is None:
        DATA_STORE = DataStore()
        FEEDBACK_ENGINE = AdaptivePersonalizationEngine(DATA_STORE)
    return DATA_STORE, FEEDBACK_ENGINE


class RouterHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for notification router REST endpoints."""

    def _send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_GET(self):
        """Handle GET requests for /health, /api/v1/status, and /api/v1/metrics."""
        ds, feedback = get_datastore()

        if self.path in ["/", "/health", "/api/v1/status"]:
            self._send_json_response({
                "status": "healthy",
                "service": "whatsapp-notification-router",
                "version": "1.1.0",
                "loaded_messages": len(ds.messages),
                "loaded_users": len(ds.users),
                "loaded_groups": len(ds.groups),
                "loaded_businesses": len(ds.businesses),
            })
        elif self.path == "/api/v1/metrics":
            # Compute real-time metrics across all messages
            predictions = [classify_message(m, ds) for m in ds.messages]
            action_dist = {}
            type_dist = {}
            for p in predictions:
                action_dist[p["action"]] = action_dist.get(p["action"], 0) + 1
                type_dist[p["message_type"]] = type_dist.get(p["message_type"], 0) + 1

            self._send_json_response({
                "total_processed": len(predictions),
                "action_distribution": action_dist,
                "type_distribution": type_dist,
                "avg_confidence": sum(p["confidence"] for p in predictions) / len(predictions),
            })
        else:
            self._send_json_response({"error": "Not Found"}, 404)

    def do_POST(self):
        """Handle POST requests for /api/v1/route, /api/v1/batch-route, /api/v1/feedback."""
        ds, feedback = get_datastore()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            self._send_json_response({"error": "Invalid JSON body"}, 400)
            return

        if self.path == "/api/v1/route":
            try:
                prediction = classify_message(payload, ds)
                # Apply personalized feedback adjustments if available
                user_id = payload.get("user_id")
                adj_action, adj_conf = feedback.adjust_action_preference(
                    user_id, prediction["action"], prediction["confidence"]
                )
                prediction["action"] = adj_action
                prediction["confidence"] = round(adj_conf, 2)
                self._send_json_response(prediction, 200)
            except Exception as e:
                self._send_json_response({"error": str(e)}, 400)

        elif self.path == "/api/v1/batch-route":
            try:
                msg_list = payload.get("messages", [])
                results = []
                for msg in msg_list:
                    pred = classify_message(msg, ds)
                    results.append(pred)
                self._send_json_response({"count": len(results), "predictions": results}, 200)
            except Exception as e:
                self._send_json_response({"error": str(e)}, 400)

        elif self.path == "/api/v1/feedback":
            try:
                uid = payload.get("user_id")
                action = payload.get("action_taken")
                response = payload.get("user_response")  # 'opened', 'dismissed', 'reported'
                feedback.record_user_action(uid, action, response)
                self._send_json_response({
                    "status": "recorded",
                    "user_id": uid,
                    "updated_profile": feedback.user_profiles.get(uid),
                }, 200)
            except Exception as e:
                self._send_json_response({"error": str(e)}, 400)
        else:
            self._send_json_response({"error": "Not Found"}, 404)


def run_server(port=8080):
    """Start local HTTP microservice server."""
    get_datastore()
    server_address = ("", port)
    httpd = HTTPServer(server_address, RouterHTTPRequestHandler)
    print(f"Server running at http://localhost:{port}/")
    return httpd


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    server = run_server(port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.")
