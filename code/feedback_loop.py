"""
Feedback Loop & Adaptive Personalization Engine:
Dynamically updates user interaction profiles and computes adaptive routing thresholds
based on recent dismissal rate, open rate, and report history.
"""


class AdaptivePersonalizationEngine:
    """Adaptive user personalization model."""

    def __init__(self, data_store):
        self.data_store = data_store
        self.user_profiles = {}
        self._initialize_profiles()

    def _initialize_profiles(self):
        """Initialize user profile weights from DataStore historical metrics."""
        for uid, udata in self.data_store.users.items():
            opened = udata.get("opened_30d", 0)
            dismissed = udata.get("dismissed_30d", 0)
            reported = udata.get("reported_30d", 0)
            total = opened + dismissed

            dismiss_ratio = dismissed / max(total, 1) if total > 0 else 0.3
            open_ratio = opened / max(total, 1) if total > 0 else 0.5

            # Calculate personalized sensitivity score (-1.0 to +1.0)
            # Positive -> prefers notify; Negative -> prefers digest/mute
            sensitivity = (open_ratio * 0.6) - (dismiss_ratio * 0.8) - (reported * 0.2)

            self.user_profiles[uid] = {
                "sensitivity": max(-1.0, min(1.0, sensitivity)),
                "dismiss_ratio": dismiss_ratio,
                "open_ratio": open_ratio,
                "reported_count": reported,
            }

    def record_user_action(self, user_id, action_taken, user_response):
        """
        Record a real-time user reaction (e.g. 'opened', 'dismissed', 'reported')
        and dynamically update the user's personalization profile.
        """
        profile = self.user_profiles.get(user_id)
        if not profile:
            return

        if user_response == "opened" and action_taken == "digest":
            # User opened a digest item -> increase sensitivity slightly
            profile["sensitivity"] = min(1.0, profile["sensitivity"] + 0.05)
        elif user_response == "dismissed" and action_taken == "notify":
            # User dismissed a notification -> decrease sensitivity (more cautious notify)
            profile["sensitivity"] = max(-1.0, profile["sensitivity"] - 0.08)
        elif user_response == "reported":
            # User reported message -> lower sensitivity significantly
            profile["sensitivity"] = max(-1.0, profile["sensitivity"] - 0.20)
            profile["reported_count"] += 1

    def adjust_action_preference(self, user_id, base_action, confidence):
        """
        Adjust prediction action and confidence based on personalized user profile.
        """
        profile = self.user_profiles.get(user_id)
        if not profile:
            return base_action, confidence

        sensitivity = profile["sensitivity"]

        # High dismissal sensitivity -> downgrade low-confidence notify to digest
        if sensitivity < -0.3 and base_action == "notify" and confidence < 0.85:
            return "digest", confidence * 0.95

        # Highly engaged user -> upgrade high-confidence digest to notify
        if sensitivity > 0.4 and base_action == "digest" and confidence > 0.82:
            return "notify", confidence * 1.02

        return base_action, confidence
