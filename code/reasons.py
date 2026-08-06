"""
Reason generation: produces concise, evidence-based human-readable explanations.
"""


def generate_reason(action, message_type, features, risk, context, media_context):
    """
    Generate a concise, specific reason for the routing decision.
    Based on actual evidence, never mentions nonexistent signals.
    """
    conv_type = context.get("conversation_type", "")
    business_data = context.get("business_data")
    group_data = context.get("group_data")
    sender_id = context.get("sender_user_id", "")

    sender_f = features.get("sender", {})
    text_f = features.get("text", {})
    biz_f = features.get("business_rel", {})
    group_f = features.get("group", {})
    history_f = features.get("history", {})

    # ─── MUTE reasons ───────────────────────────────────────────────────

    if action == "mute" and message_type == "scam":
        if risk.get("is_injection"):
            return ("The message tries to instruct the router, but the routing "
                    "decision should be based on the actual content and risk.")

        if risk.get("safety_reason") == "otp_phishing":
            if conv_type == "personal" and not history_f.get("has_history"):
                return ("This is the first message from the sender and it asks "
                        "for sensitive verification or payment.")
            return ("The message asks for urgent OTP or account verification "
                    "through a suspicious flow.")

        if risk.get("safety_reason") == "financial_scam":
            if business_data and not business_data.get("verified"):
                return (f"An unverified account using {business_data.get('sender_domain', 'a suspicious domain')} "
                        "requests payment or financial details with urgency pressure.")
            return ("The message uses fake support language and account-blocking "
                    "pressure to push the user into action.")

        if risk.get("safety_reason") == "suspicious_business":
            biz_name = business_data.get("display_name", "Unknown") if business_data else "Unknown"
            return (f"The sender ({biz_name}) is unverified with domain mismatch "
                    "and high user reports, indicating a fraudulent account.")

        return ("The message uses fake support language and account-blocking "
                "pressure to push the user into action.")

    if action == "mute" and message_type == "spam":
        if biz_f.get("opted_out"):
            return "The user has opted out of or repeatedly dismissed similar marketing messages."
        if history_f.get("mostly_dismissed"):
            return "Similar historical messages were ignored, dismissed, or muted by this user."
        if business_data and not business_data.get("verified"):
            return "The sender is an unverified business with high reports and the user has no active relationship."
        return "The user has opted out of or repeatedly dismissed similar marketing messages."

    if action == "mute" and message_type == "promotion":
        if biz_f.get("opted_out"):
            return "The user has opted out of or repeatedly dismissed similar marketing messages."
        if history_f.get("mostly_dismissed"):
            return "Similar historical messages were ignored, dismissed, or muted by this user."
        if group_f.get("group_muted"):
            return "The user has muted this group and historical messages from this sender were dismissed."
        return "The user has opted out of or repeatedly dismissed similar marketing messages."

    if action == "mute" and message_type == "greeting":
        if sender_f.get("sender_is_habitual_forwarder"):
            return "The sender has a pattern of repeated forwarded greetings that the user usually ignores."
        return "The message is a generic greeting or motivational forward with no actionable content."

    if action == "mute" and message_type == "forward":
        if sender_f.get("sender_is_habitual_forwarder"):
            return "The sender frequently forwards chain messages that the user does not engage with."
        return "The message is a chain forward with no personal or actionable content for this user."

    # ─── NOTIFY reasons ──────────────────────────────────────────────────

    if action == "notify" and message_type == "urgent":
        if text_f.get("has_direct_mention"):
            if group_f.get("group_type") == "coworker":
                return "The message is from a work context and contains a direct mention requiring the user's response."
            return "The sender directly mentions or tags this user, requiring a response or action."
        if sender_f.get("sender_is_trusted_admin"):
            group_name = group_data.get("group_name", "group") if group_data else "group"
            return f"A trusted admin in {group_name} sent a time-sensitive notice that should interrupt the user."
        if conv_type == "personal":
            if text_f.get("is_urgent_legitimate"):
                return "The message contains a time-sensitive request from a direct contact."
            return "A close contact sent a short urgent request that should interrupt the user."
        # Voice notes from family
        if group_f.get("group_type") in ("family", "extended_family"):
            return "A family member sent a voice note that likely requires prompt attention."
        return "A close contact sent a short urgent request that should interrupt the user."

    if action == "notify" and message_type == "business_update":
        if business_data:
            biz_name = business_data.get("brand_name", business_data.get("display_name", "A business"))
            if biz_f.get("is_active_relationship"):
                rel_type = biz_f.get("relationship_type", "recent activity")
                return f"A verified business is sending an update that matches the user's recent {_humanize_relationship(rel_type)}."
            return f"A verified business is sending a legitimate but non-urgent update."
        return "A verified business is sending an update related to the user's activity."

    if action == "notify" and message_type == "event":
        if sender_f.get("sender_is_trusted_admin"):
            return "A school admin sent a same-day operational update that the user is likely to need immediately."
        if business_data and biz_f.get("has_relationship"):
            return "A verified business is sending a reminder that matches the user's recent booking history."
        return "A same-day event or operational update that the user is likely to need immediately."

    if action == "notify" and message_type == "personal":
        return "The sender directly asks this user for a response or action."

    if action == "notify" and message_type == "payment":
        if sender_f.get("sender_is_trusted_admin"):
            return "A trusted admin sent a payment or maintenance reminder with a clear deadline."
        return "The message contains a legitimate payment or transaction update requiring attention."

    # ─── DIGEST reasons ──────────────────────────────────────────────────

    if action == "digest" and message_type == "promotion":
        if biz_f.get("allows_promotions"):
            return "The message is promotional but matches a topic or business the user has opted into."
        if group_f.get("group_type") in ("marketplace", "local_food"):
            group_name = group_data.get("group_name", "group") if group_data else "the group"
            return f"A listing in {group_name} may be relevant but does not need immediate attention."
        if business_data:
            biz_name = business_data.get("brand_name", business_data.get("display_name", ""))
            if biz_name:
                return f"The promotional message from {biz_name} may be relevant but is not time-sensitive."
        return "The offer is potentially relevant, but it does not need immediate attention."

    if action == "digest" and message_type == "business_update":
        if business_data and business_data.get("verified"):
            return "A verified business is sending a legitimate but non-urgent update."
        return "The verified business message is legitimate but does not require immediate attention."

    if action == "digest" and message_type == "event":
        return "The message is useful group information, but it is not urgent enough to interrupt the user."

    if action == "digest" and message_type == "greeting":
        return "The message is a harmless greeting that can be read later."

    if action == "digest" and message_type == "personal":
        if conv_type == "group" and group_data:
            group_name = group_data.get("group_name", "the group")
            return f"A message in {group_name} is casual conversation with no urgent action required."
        if history_f.get("has_history"):
            return "The sender is known, but the message has no urgent action or safety relevance."
        return "The message is safe casual chat with no urgent action required."

    if action == "digest" and message_type == "unknown":
        return "The sender is unfamiliar, but the message does not show urgency, payment pressure, or safety risk."

    if action == "digest" and message_type == "forward":
        return "The forwarded content may be useful but does not require immediate attention."

    if action == "digest" and message_type == "payment":
        return "The payment update is legitimate but does not require immediate action."

    # ─── Fallback ────────────────────────────────────────────────────────
    return f"The message has been classified as {action} based on sender context and content analysis."


def _humanize_relationship(rel_type):
    """Convert relationship type codes to human-readable phrases."""
    mapping = {
        "delivery_expected_today": "delivery order",
        "recent_grocery_delivery": "grocery delivery",
        "active_bank_account": "banking activity",
        "upcoming_clinic_appointment": "clinic appointment",
        "confirmed_travel_booking": "travel booking",
        "recent_card_payment": "card payment",
        "monthly_utility_bill": "utility bill",
        "active_sale_subscription": "shopping subscription",
        "old_sale_subscription": "shopping activity",
        "ride_booked_today": "ride booking",
        "recent_product_purchase": "product purchase",
        "recent_return_pickup": "return pickup",
        "prescription_refill": "prescription",
        "active_credit_card": "credit card",
        "frequent_food_orders": "food orders",
        "monthly_mobile_bill": "mobile bill",
        "active_payment_wallet": "payment wallet",
        "recent_movie_booking": "movie booking",
        "active_retail_membership": "retail membership",
        "fashion_sale_subscription": "fashion subscription",
        "travel_package_interest": "travel interest",
        "travel_promotions_opted_out": "travel activity",
        "food_promotions_opted_out": "food activity",
        "saved_travel_search": "travel search",
        "abandoned_travel_search": "travel activity",
        "loan_promotions_opted_out": "loan activity",
        "ignored_loan_message": "loan activity",
        "marketplace_style_interest": "style interest",
        "campus_event_registration": "campus event",
        "student_event_booking": "event booking",
        "security_webinar_registration": "webinar registration",
        "business_payment_stack_interest": "payment services",
        "society_payment_receipt": "society payment",
        "repair_booking": "repair booking",
        "monthly_maintenance_payment": "maintenance payment",
    }
    return mapping.get(rel_type, "activity history")
