from flask import jsonify, request

from ..services.api_keys import _save_api_key, provider_status
from ..services.providers import ProviderRequiredError, provider_required_response


def register_provider_routes(app):
    @app.route("/api/providers/status")
    def api_provider_status():
        return jsonify({"success": True, "providers": provider_status(), "required_primary": "groq", "alternate": "gemini"})

    @app.route("/api/providers/key", methods=["POST"])
    def api_provider_key():
        payload = request.get_json(silent=True) or {}
        provider = str(payload.get("provider") or "").lower().strip()
        key = str(payload.get("api_key") or "").strip()
        try:
            _save_api_key(provider, key)
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        return jsonify({"success": True, "provider": provider, "providers": provider_status(), "message": f"{provider.title()} API key saved for future use."})