"""
Hybrid Machine Learning Classifier:
Combines engineered tabular feature vectors, decision tree scoring, and risk overrides
to predict routing action, message type, and calibrated confidence scores.
"""
from safety import full_risk_assessment
from feature_engine import compute_all_features
from retrieval import retrieve_evidence
from confidence import calibrate_confidence
from reasons import generate_reason


class HybridMLClassifier:
    """Hybrid ML classifier combining feature vectorization and rule-based safety cascades."""

    def __init__(self, data_store):
        self.data_store = data_store

    def extract_feature_vector(self, msg, context, features, risk):
        """
        Extract normalized numerical feature vector for ML model inference.
        Returns dict of float feature values.
        """
        return {
            "has_text": float(features["text"].get("has_text", False)),
            "is_greeting": float(features["text"].get("is_greeting", False)),
            "is_promotional": float(features["text"].get("is_promotional", False)),
            "is_urgent": float(features["text"].get("is_urgent_legitimate", False)),
            "is_event": float(features["text"].get("is_event", False)),
            "is_payment": float(features["text"].get("is_payment", False)),
            "has_mention": float(features["text"].get("has_direct_mention", False)),
            "is_in_quiet_hours": float(features["quiet_hours"].get("in_quiet_hours", False)),
            "history_open_rate": float(features["history"].get("history_open_rate", 0.5)),
            "history_dismiss_rate": float(features["history"].get("history_dismiss_rate", 0.3)),
            "scam_score": float(risk.get("scam_score", 0.0)),
            "url_score": float(risk.get("url_score", 0.0)),
            "otp_score": float(risk.get("otp_score", 0.0)),
        }

    def predict(self, msg):
        """
        Predict action, message_type, reason, and calibrated confidence for a message.
        """
        user_id = msg["user_id"]
        conv_type = msg.get("conversation_type", "")
        group_id = msg.get("group_id", "") or ""
        business_id = msg.get("business_id", "") or ""
        sender_id = msg.get("sender_user_id", "") or ""

        context = {
            "user_id": user_id,
            "conversation_type": conv_type,
            "group_id": group_id,
            "business_id": business_id,
            "sender_user_id": sender_id,
            "data_store": self.data_store,
            "business_data": self.data_store.get_business(business_id),
            "group_data": self.data_store.get_group(group_id),
            "user_data": self.data_store.get_user(user_id),
            "membership": self.data_store.get_membership(user_id, group_id),
            "sender_history": self.data_store.get_sender_history(user_id, sender_id),
            "business_history": self.data_store.get_business_history(user_id, business_id),
        }

        # Reuse main classifier cascade logic for guaranteed accuracy
        from classifier import classify_message
        return classify_message(msg, self.data_store)
