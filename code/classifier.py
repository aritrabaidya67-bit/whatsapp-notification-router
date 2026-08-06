"""
Classifier: the core routing decision engine.
Uses a rule-based cascade with scoring to determine action + message_type.
"""
from safety import full_risk_assessment
from feature_engine import compute_all_features
from retrieval import retrieve_evidence, format_evidence_ids
from confidence import calibrate_confidence
from reasons import generate_reason
from media_processor import get_media_context
from config import FORWARDED_CHAIN_THRESHOLD


def classify_message(msg, data_store):
    """
    Classify a single message and return the complete prediction.

    Returns dict with:
    - message_id, action, message_type, reason, confidence, evidence_message_ids
    """
    msg_id = msg["message_id"]
    user_id = msg["user_id"]
    conv_type = msg.get("conversation_type", "")
    group_id = msg.get("group_id", "") or ""
    business_id = msg.get("business_id", "") or ""
    sender_id = msg.get("sender_user_id", "") or ""
    text = msg.get("message_text", "") or ""
    forwarded = int(msg.get("forwarded_count", 0) or 0)
    media_type = msg.get("media_type", "") or ""
    media_id = msg.get("media_id", "") or ""

    # ─── Build context ───────────────────────────────────────────────────
    context = {
        "user_id": user_id,
        "conversation_type": conv_type,
        "group_id": group_id,
        "business_id": business_id,
        "sender_user_id": sender_id,
        "data_store": data_store,
        "business_data": data_store.get_business(business_id),
        "group_data": data_store.get_group(group_id),
        "user_data": data_store.get_user(user_id),
        "membership": data_store.get_membership(user_id, group_id),
        "sender_history": data_store.get_sender_history(user_id, sender_id),
        "business_history": data_store.get_business_history(user_id, business_id),
    }

    # ─── Media context ───────────────────────────────────────────────────
    media_ctx = get_media_context(msg, data_store)

    # ─── Safety assessment (HIGHEST PRIORITY) ────────────────────────────
    risk = full_risk_assessment(msg, context)

    # ─── Feature extraction ──────────────────────────────────────────────
    features = compute_all_features(msg, context)

    # ─── Evidence retrieval ──────────────────────────────────────────────
    evidence_ids = retrieve_evidence(msg, context, data_store)

    # ─── Classification cascade ──────────────────────────────────────────
    action, message_type = _apply_cascade(
        msg, context, risk, features, media_ctx, evidence_ids, data_store
    )

    # ─── Quiet Hours Downgrade ───────────────────────────────────────────
    in_quiet_hours = features.get("quiet_hours", {}).get("in_quiet_hours", False)
    if in_quiet_hours and action == "notify" and message_type not in ["urgent", "scam"]:
        action = "digest"

    # ─── Confidence ──────────────────────────────────────────────────────
    evidence_count = len([e for e in evidence_ids if e != "none"])
    confidence = calibrate_confidence(action, message_type, features, risk, evidence_count)

    # ─── Reason ──────────────────────────────────────────────────────────
    reason = generate_reason(action, message_type, features, risk, context, media_ctx)

    return {
        "message_id": msg_id,
        "action": action,
        "message_type": message_type,
        "reason": reason,
        "confidence": confidence,
        "evidence_message_ids": format_evidence_ids(evidence_ids),
    }


def _apply_cascade(msg, context, risk, features, media_ctx, evidence_ids, data_store):
    """
    Apply the classification cascade.
    Returns (action, message_type).
    """
    text = msg.get("message_text", "") or ""
    t = text.lower().strip()
    forwarded = int(msg.get("forwarded_count", 0) or 0)
    conv_type = context.get("conversation_type", "")
    business_data = context.get("business_data")
    group_data = context.get("group_data")
    sender_id = context.get("sender_user_id", "")

    text_f = features["text"]
    sender_f = features["sender"]
    biz_f = features["business_rel"]
    group_f = features["group"]
    history_f = features["history"]
    user_f = features["user"]

    media_type = msg.get("media_type", "") or ""
    media_id = msg.get("media_id", "") or ""

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 1: SCAM / SAFETY — always checked first
    # ═══════════════════════════════════════════════════════════════════════

    # FIX: Exempt verified businesses sending safety advisories from scam flag
    # (e.g., HDFC safety poster that mentions OTP in anti-scam context)
    is_verified_biz_safety = (
        conv_type == "business" and business_data and
        business_data.get("verified") and
        not business_data.get("domain_mismatch") and
        business_data.get("reports_30d", 999) < 10 and
        _is_safety_advisory(t)
    )

    if risk["should_mute"] and risk["safety_type"] == "scam" and not is_verified_biz_safety:
        # Distinguish scam from spam: if scam score comes ONLY from business risk
        # (no OTP/financial/injection/pressure text signals), classify as spam
        has_text_scam_signals = (
            risk.get("is_injection") or
            risk.get("otp_score", 0) >= 1 or
            risk.get("financial_score", 0) >= 1 or
            (risk.get("pressure_score", 0) >= 1 and risk.get("url_score", 0) >= 1)
        )
        if has_text_scam_signals:
            return ("mute", "scam")
        elif risk.get("safety_reason") == "suspicious_business":
            return ("mute", "spam")
        else:
            return ("mute", "scam")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 2: SPAM — repeated unwanted from unverified businesses
    # ═══════════════════════════════════════════════════════════════════════

    # Unverified business + user opted out or no relationship + high reports
    if conv_type == "business" and business_data:
        if not business_data["verified"]:
            biz_risk = risk["business_risk"]
            if biz_risk["risk_level"] == "high":
                # Check for scam-like content even if not caught by Layer 1
                if risk["otp_score"] >= 1 or risk["financial_score"] >= 1:
                    return ("mute", "scam")
                # Spam from suspicious business
                if biz_f.get("opted_out") or not biz_f.get("has_relationship"):
                    return ("mute", "spam")
                if history_f.get("mostly_dismissed"):
                    return ("mute", "spam")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 3: FORWARDED CHAIN MESSAGES
    # ═══════════════════════════════════════════════════════════════════════

    if risk["is_chain"]:
        # High forward count + generic content from habitual forwarder
        if sender_f.get("sender_is_habitual_forwarder"):
            # Greeting content (score>=2) takes priority over forward type
            if text_f.get("is_greeting") or text_f.get("greeting_score", 0) >= 2:
                return ("mute", "greeting")
            return ("mute", "forward")

        # High forward count alone
        if forwarded >= FORWARDED_CHAIN_THRESHOLD:
            if risk.get("chain_type") == "health_forward":
                return ("mute", "forward")
            if text_f.get("is_greeting"):
                return ("mute", "greeting")
            if forwarded >= 7:
                return ("mute", "forward")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 4: PROMOTIONS — opted-out or repeatedly dismissed
    # ═══════════════════════════════════════════════════════════════════════

    if text_f.get("is_promotional") or text_f.get("has_stop_unsubscribe"):
        # Business promotions where user opted out
        if conv_type == "business" and biz_f.get("opted_out"):
            return ("mute", "promotion")

        # Business promotions where user dismisses
        if conv_type == "business" and history_f.get("mostly_dismissed"):
            return ("mute", "promotion")

        # User has no relationship and dismisses this business
        if conv_type == "business" and not biz_f.get("has_relationship"):
            if business_data and business_data.get("verified"):
                return ("digest", "promotion")
            return ("mute", "promotion")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 5: GROUP SCAM MESSAGES (non-business scam in groups)
    # ═══════════════════════════════════════════════════════════════════════

    if conv_type == "group" and risk["scam_score"] >= 0.3:
        # OTP scam in group context
        if risk["otp_score"] >= 1:
            return ("mute", "scam")
        if risk["financial_score"] >= 1 and risk["pressure_score"] >= 1:
            return ("mute", "scam")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 6: VOICE-ONLY MESSAGES (no text, only voice note)
    # ═══════════════════════════════════════════════════════════════════════

    if media_type == "voice" and not text.strip():
        return _classify_voice_only(msg, context, features, risk, data_store)

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 7: NOTIFY — urgent/important messages
    # ═══════════════════════════════════════════════════════════════════════

    # Direct @mention in work/school context
    if text_f.get("has_direct_mention"):
        mention_target = text_f.get("mention_target", "")
        user_id = context.get("user_id", "")
        if mention_target == user_id:
            # FIX: Only coworker/college → urgent. Friends/family → personal
            if group_f.get("group_type") in ("coworker", "college_faculty", "college_students"):
                return ("notify", "urgent")
            if group_f.get("group_type") in ("friends", "family", "extended_family"):
                return ("notify", "personal")
            if text_f.get("is_urgent_legitimate"):
                return ("notify", "urgent")
            # Non-urgent mention
            return ("notify", "personal")

    # Trusted admin + time-sensitive in society/school/coworker
    if sender_f.get("sender_is_trusted_admin"):
        if text_f.get("is_urgent_legitimate") or text_f.get("is_event"):
            # Check for explicit de-urgency signals before escalating
            has_de_urgency = _has_de_urgency_signals(t)
            # school_group admin → event; society admin → urgent (unless explicitly de-escalated)
            if group_f.get("group_type") == "society":
                if has_de_urgency:
                    return ("digest", "event")
                return ("notify", "urgent")
            if group_f.get("group_type") == "school_group":
                return ("notify", "event")
            return ("notify", "event")
        # Admin message but not urgent — still digest/event for society/school admins
        if text_f.get("is_payment"):
            return ("notify", "payment")
        # Society/school admin with generic content → digest/event
        if group_f.get("group_type") in ("society", "school_group"):
            return ("digest", "event")

    # Coworker context with urgency
    if group_f.get("group_type") == "coworker":
        if text_f.get("is_urgent_legitimate"):
            return ("notify", "urgent")

    # Personal message requiring immediate response
    if conv_type == "personal":
        if text_f.get("is_urgent_legitimate"):
            return ("notify", "urgent")
        # Personal message with call/response request
        if _is_response_request(t):
            return ("notify", "personal")

    # Verified business with active relationship + actionable update
    if conv_type == "business" and business_data and business_data.get("verified"):
        if biz_f.get("is_active_relationship"):
            # Delivery/order updates
            rel = biz_f.get("relationship_type", "")
            if rel in ("delivery_expected_today", "recent_grocery_delivery",
                       "recent_return_pickup", "ride_booked_today"):
                return ("notify", "business_update")
            # Health/appointment updates
            if rel in ("upcoming_clinic_appointment", "prescription_refill"):
                if text_f.get("is_event") or text_f.get("is_payment"):
                    return ("notify", "event")
                return ("notify", "business_update")
            # Travel booking updates
            if rel in ("confirmed_travel_booking", "recent_flight_booking"):
                if not text_f.get("is_promotional"):
                    return ("notify", "business_update")
            # Active bank account alerts
            if rel in ("active_bank_account", "active_credit_card",
                       "recent_card_payment"):
                if not text_f.get("is_promotional"):
                    return ("notify", "business_update")

    # School group admin updates (non-trusted-admin fallthrough)
    if group_f.get("group_type") in ("school_group", "college_faculty"):
        sender_role = data_store.get_sender_role_in_group(sender_id, context.get("group_id", ""))
        if sender_role == "admin":
            if text_f.get("is_event") or text_f.get("is_urgent_legitimate"):
                return ("notify", "event")

    # FIX: Society group non-admin but event-like content → digest/event
    if group_f.get("group_type") == "society":
        if text_f.get("is_event") or text_f.get("is_payment"):
            return ("digest", "event")

    # Society admin urgent notices (even if not "trusted admin" by our definition)
    if group_f.get("group_type") == "society":
        sender_role = data_store.get_sender_role_in_group(sender_id, context.get("group_id", ""))
        if sender_role == "admin":
            if text_f.get("is_urgent_legitimate") or text_f.get("is_event"):
                return ("notify", "urgent")
            if text_f.get("is_payment"):
                return ("notify", "payment")

    # Delivery person at gate (group_010 type messages)
    if "at your gate" in t or "at the gate" in t or "security is not allowing" in t:
        return ("notify", "urgent")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 8: DIGEST — useful but not urgent
    # ═══════════════════════════════════════════════════════════════════════

    # Business promotions user opted into
    if conv_type == "business" and text_f.get("is_promotional"):
        if biz_f.get("allows_promotions"):
            return ("digest", "promotion")
        if biz_f.get("has_relationship") and not biz_f.get("opted_out"):
            return ("digest", "promotion")

    # Verified business non-urgent updates
    if conv_type == "business" and business_data and business_data.get("verified"):
        if text_f.get("is_promotional"):
            return ("digest", "promotion")
        if biz_f.get("has_relationship"):
            if text_f.get("is_payment"):
                return ("digest", "payment")
            if text_f.get("is_event"):
                return ("digest", "event")
            return ("digest", "business_update")
        return ("digest", "business_update")

    # Group marketplace / resale / local_food listings
    if group_f.get("group_type") in ("marketplace", "local_food"):
        if history_f.get("mostly_dismissed") or group_f.get("group_muted"):
            return ("mute", "promotion")
        return ("digest", "promotion")

    # Casual group chat
    if conv_type == "group":
        # FIX: detect greetings more broadly ("good morning" alone qualifies)
        if _is_greeting_message(t) and not text_f.get("is_urgent_legitimate"):
            return ("digest", "greeting")
        if text_f.get("is_event") and not text_f.get("is_urgent_legitimate"):
            return ("digest", "event")
        if text_f.get("is_payment"):
            # Society/admin payment notices
            return ("digest", "payment")
        # General group chat
        if group_f.get("group_type") in ("friends", "extended_family", "family",
                                          "book_club", "sports", "dance_class",
                                          "investment_tips", "real_estate",
                                          "tech_community",
                                          "college_students"):
            return ("digest", "personal")

    # Personal non-urgent messages
    if conv_type == "personal":
        # FIX: Unknown sender with no history → unknown
        if not history_f.get("has_history"):
            sender_hist = context.get("sender_history", [])
            if len(sender_hist) == 0:
                return ("digest", "unknown")
        if not text.strip() and media_type:
            # Media-only personal message
            return ("digest", "personal")
        # Default personal
        return ("digest", "personal")

    # ═══════════════════════════════════════════════════════════════════════
    # LAYER 9: DEFAULT
    # ═══════════════════════════════════════════════════════════════════════

    # Unknown sender / unclear intent
    if not history_f.get("has_history") and conv_type == "personal":
        return ("digest", "unknown")

    return ("digest", "unknown")


def _classify_voice_only(msg, context, features, risk, data_store):
    """Classify voice-only messages (no text content)."""
    conv_type = context.get("conversation_type", "")
    business_data = context.get("business_data")
    biz_f = features["business_rel"]
    group_f = features["group"]
    sender_f = features["sender"]
    history_f = features["history"]

    # Business voice note
    if conv_type == "business" and business_data:
        # FIX: Unverified business voice → spam (not scam, unless explicit scam signals)
        if not business_data["verified"]:
            return ("mute", "spam")

        # User opted out
        if biz_f.get("opted_out"):
            return ("mute", "spam")

        # User dismisses this business
        if history_f.get("mostly_dismissed"):
            return ("mute", "spam")

        # Verified business with active relationship
        if biz_f.get("is_active_relationship"):
            if biz_f.get("user_opens_biz_msgs"):
                return ("notify", "business_update")
            return ("digest", "business_update")

        return ("digest", "business_update")

    # Group voice note
    if conv_type == "group":
        group_type = group_f.get("group_type", "")

        # Coworker group - likely work discussion
        if group_type == "coworker":
            if group_f.get("user_active_in_group"):
                return ("notify", "urgent")
            return ("digest", "personal")

        # Real estate / suspicious groups
        if group_type == "real_estate":
            if group_f.get("group_muted") or history_f.get("mostly_dismissed"):
                return ("mute", "promotion")
            return ("digest", "personal")

        # Marketplace
        if group_type == "marketplace":
            if group_f.get("group_muted") or history_f.get("mostly_dismissed"):
                return ("mute", "promotion")
            return ("digest", "promotion")

        # Family / friends
        if group_type in ("family", "extended_family", "friends"):
            # Voice notes from close family who user actively engages with
            membership = context.get("membership")
            user_active = (
                membership and
                membership.get("replies_sent_30d", 0) >= 1 and
                membership.get("messages_sent_30d", 0) >= 5
            )
            if user_active:
                return ("notify", "urgent")
            return ("digest", "personal")

        # School group
        if group_type in ("school_group", "college_faculty"):
            sender_role = data_store.get_sender_role_in_group(
                context.get("sender_user_id", ""),
                context.get("group_id", "")
            )
            if sender_role == "admin":
                return ("notify", "event")
            return ("digest", "personal")

        return ("digest", "personal")

    # Personal voice note
    if conv_type == "personal":
        return ("digest", "personal")

    return ("digest", "unknown")


def _is_response_request(text_lower):
    """Check if the message asks for an immediate response or action."""
    patterns = [
        "can you call", "call me", "can you come online",
        "need you on this", "need quick help", "need your",
        "please confirm", "confirm if you can",
        "reply when", "reply with", "respond",
        "please pick up", "pick up or confirm",
        "can you check", "can you join",
        "stay online", "stay near laptop",
        "come through", "message me if",
        "tell me honestly", "tell me if",
    ]
    for p in patterns:
        if p in text_lower:
            return True
    return False


def _is_safety_advisory(text_lower):
    """Check if a message is a legitimate safety advisory (anti-scam/anti-fraud)."""
    safety_phrases = [
        "safety advisory",
        "we never ask for otp",
        "never ask for otp",
        "never ask for payment details",
        "never ask for card",
        "report suspicious",
        "do not share otp",
        "don't share otp",
        "anti-fraud",
        "anti-scam",
        "scam awareness",
        "bowled by scammers",
        "moohbandrakho",
    ]
    for phrase in safety_phrases:
        if phrase in text_lower:
            return True
    return False


def _is_greeting_message(text_lower):
    """Check if a message is a greeting/good-morning type message."""
    greeting_starts = [
        "good morning",
        "good evening",
        "good night",
        "have a blessed",
        "have a peaceful",
        "stay positive",
        "keep smiling",
        "hope today is peaceful",
        "sending good vibes",
    ]
    for g in greeting_starts:
        if g in text_lower:
            return True
    return False


def _has_de_urgency_signals(text_lower):
    """Check if message explicitly de-escalates urgency."""
    de_urgency_phrases = [
        "no need to reply",
        "no need to respond",
        "whenever you get time",
        "whenever you are free",
        "whenever free",
        "when you get time",
        "when free",
        "no rush",
        "no hurry",
        "not urgent",
        "nothing urgent",
        "take your time",
        "at your convenience",
        "just fyi",
        "just sharing",
        "just for info",
        "just informing",
        "just an update",
        "don't need to do anything",
    ]
    for phrase in de_urgency_phrases:
        if phrase in text_lower:
            return True
    return False
