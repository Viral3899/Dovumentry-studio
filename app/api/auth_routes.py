import os
from flask import jsonify, request, session
from werkzeug.security import check_password_hash

from ..services.auth import (
    find_user, set_authenticated_user, authentication_configured,
    google_auth_configured
)
from ..services.errors import record_error
from ..services.api_keys import provider_status


def register_auth_routes(app):
    @app.route("/api/auth/login", methods=["POST"])
    def admin_login():
        payload = request.get_json(silent=True) or {}
        username = (payload.get("identifier") or payload.get("username") or "").strip()
        password = payload.get("password") or ""
        requested_role = (payload.get("role") or "admin").strip().lower()
        if requested_role not in {"admin", "user"}:
            return jsonify({"success": False, "message": "Choose a valid account type."}), 400
        if not authentication_configured():
            return jsonify({"success": False, "message": "Authentication is not configured."}), 503
        account = find_user(username, requested_role)
        if not account:
            return jsonify({"success": False, "message": f"Invalid {requested_role} credentials."}), 401
        configured_username = account["username"] if isinstance(account, dict) else account[0]
        role = account["role"] if isinstance(account, dict) else account[3]
        password_hash = account["password_hash"] if isinstance(account, dict) else account[4]
        try:
            valid = check_password_hash(password_hash, password)
        except ValueError:
            valid = False
        if not valid:
            return jsonify({"success": False, "message": f"Invalid {requested_role} credentials."}), 401
        set_authenticated_user(configured_username, role)
        return jsonify({"success": True, "username": configured_username, "role": role})

    @app.route("/api/auth/google", methods=["POST"])
    def google_login():
        credential = (request.get_json(silent=True) or {}).get("credential")
        if not credential or not google_auth_configured():
            return jsonify({"success": False, "message": "Google sign-in is not configured."}), 503
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            claims = id_token.verify_oauth2_token(credential, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID"))
        except Exception:
            return jsonify({"success": False, "message": "Google sign-in could not be verified."}), 401
        email = (claims.get("email") or "").strip().lower()
        if not claims.get("email_verified"):
            return jsonify({"success": False, "message": "Use a verified Google email address."}), 401
        admin_email = os.getenv("GOOGLE_ADMIN_EMAIL", "").strip().lower()
        user_email = os.getenv("GOOGLE_USER_EMAIL", "").strip().lower()
        if email == admin_email:
            role = "admin"
        elif email == user_email:
            role = "user"
        else:
            return jsonify({"success": False, "message": "This Google account is not allowed."}), 403
        set_authenticated_user(claims.get("name") or email, role, email)
        return jsonify({"success": True, "username": claims.get("name") or email, "email": email, "role": role})

    @app.route("/api/auth/me")
    def admin_me():
        authenticated = bool(session.get("authenticated"))
        return jsonify({
            "success": True,
            "authenticated": authenticated or not authentication_configured(),
            "username": session.get("username") if authenticated else (os.getenv("ADMIN_USERNAME", "admin") if not authentication_configured() else None),
            "role": session.get("role") if authenticated else ("admin" if not authentication_configured() else None),
            "email": session.get("email") if authenticated else None,
            "auth_configured": authentication_configured(),
            "google_configured": google_auth_configured(),
            "google_client_id": os.getenv("GOOGLE_CLIENT_ID") if google_auth_configured() else None,
        })

    @app.route("/api/auth/logout", methods=["POST"])
    def admin_logout():
        session.clear()
        return jsonify({"success": True})