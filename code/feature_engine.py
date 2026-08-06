"""
Feature engineering: computes structured features from message context.
"""
import re
from config import (
    GREETING_KEYWORDS, PROMOTIONAL_KEYWORDS,
    URGENCY_LEGITIMATE_KEYWORDS, EVENT_KEYWORDS,
    PAYMENT_KEYWORDS, FORWARDED_CHAIN_THRESHOLD,
)


def _text_lower(text):
    return (text or "").lower().strip()


def compute_text_features(text):
    """Extract text-based features from message content."""
    t = _text_lower(text)

    if not t:
        return {
            "has_text": False,
            "is_greeting": False,
            "is_promotional": False,
            "is_urgent_legitimate": False,
            "is_event": False,
            "is_payment": False,
            "has_direct_mention": False,
            "mention_target": None,
            "has_stop_unsubscribe": False,
            "word_count": 0,
        }

    # Direct @mention
    mention_match = re.search(r'@(u_\d+)', t)
    has_mention = bool(mention_match)
    mention_target = mention_match.group(1) if mention_match else None

    # Greeting score
    greeting_score = sum(1 for kw in GREETING_KEYWORDS if kw.lower() in t)

    # Promotional score
    promo_score = sum(1 for kw in PROMOTIONAL_KEYWORDS if kw.lower() in t)

    # Legitimate urgency score
    urgency_score = sum(1 for kw in URGENCY_LEGITIMATE_KEYWORDS if kw.lower() in t)

    # Event score
    event_score = sum(1 for kw in EVENT_KEYWORDS if kw.lower() in t)

    # Payment score
    payment_score = sum(1 for kw in PAYMENT_KEYWORDS if kw.lower() in t)

    # Has STOP/unsubscribe
    has_stop = "reply stop" in t or "unsubscribe" in t

    return {
        "has_text": True,
        "is_greeting": greeting_score >= 2,
        "greeting_score": greeting_score,
        "is_promotional": promo_score >= 2 or has_stop,
        "promo_score": promo_score,
        "is_urgent_legitimate": urgency_score >= 1,
        "urgency_score": urgency_score,
        "is_event": event_score >= 1,
        "event_score": event_score,
        "is_payment": payment_score >= 1,
        "payment_score": payment_score,
        "has_direct_mention": has_mention,
        "mention_target": mention_target,
        "has_stop_unsubscribe": has_stop,
        "word_count": len(t.split()),
    }


def compute_sender_features(context):
    """Compute features about the sender's trustworthiness and relationship."""
    sender_id = context.get("sender_user_id", "")
    group_id = context.get("group_id", "")
    data_store = context["data_store"]

    features = {
        "sender_is_admin": False,
        "sender_is_trusted_admin": False,
        "sender_is_habitual_forwarder": False,
    }

    if sender_id and group_id:
        role = data_store.get_sender_role_in_group(sender_id, group_id)
        if role == "admin":
            features["sender_is_admin"] = True
            # Trusted admin = admin in society/school/coworker groups
            group_data = data_store.get_group(group_id)
            if group_data and group_data["group_type"] in (
                "society", "school_group", "coworker",
                "college_faculty", "safety"
            ):
                features["sender_is_trusted_admin"] = True

    # Check if sender is a habitual forwarder (u_051 pattern)
    if sender_id:
        sender_history = data_store.get_sender_history(
            context.get("user_id", ""), sender_id
        )
        forward_count = 0
        dismissed_count = 0
        for hist in sender_history:
            fc = int(hist.get("forwarded_count", 0) or 0)
            if fc >= 3:
                forward_count += 1
            ev = data_store.get_event(hist["message_id"])
            if ev and ev.get("dismissed"):
                dismissed_count += 1

        total = len(sender_history)
        if total >= 2 and forward_count >= 2:
            features["sender_is_habitual_forwarder"] = True
        if total >= 2 and dismissed_count / max(total, 1) >= 0.5:
            features["sender_mostly_dismissed"] = True
        else:
            features["sender_mostly_dismissed"] = False

    return features


def compute_user_engagement(context):
    """Compute how the user typically engages with this type of content."""
    user_id = context.get("user_id", "")
    data_store = context["data_store"]
    user_data = data_store.get_user(user_id)

    features = {
        "user_open_rate": 0.5,
        "user_reply_rate": 0.1,
        "user_dismiss_rate": 0.3,
        "user_report_rate": 0.0,
        "notification_load": 0,
        "notification_fatigue": False,
    }

    if user_data:
        total = (user_data["opened_30d"] + user_data["dismissed_30d"])
        if total > 0:
            features["user_open_rate"] = user_data["opened_30d"] / total
            features["user_dismiss_rate"] = user_data["dismissed_30d"] / total
        if user_data["opened_30d"] > 0:
            features["user_reply_rate"] = (
                user_data["replied_30d"] / user_data["opened_30d"]
            )
        if total > 0:
            features["user_report_rate"] = user_data["reported_30d"] / total

    # Notification load
    avg_sent, avg_dismissed = data_store.get_avg_daily_notifications(user_id)
    features["notification_load"] = avg_sent
    features["notification_fatigue"] = avg_dismissed / max(avg_sent, 1) > 0.4

    return features


def compute_business_relationship_features(context):
    """Compute features about user-business relationship."""
    user_id = context.get("user_id", "")
    business_id = context.get("business_id", "")
    data_store = context["data_store"]

    features = {
        "has_relationship": False,
        "relationship_type": None,
        "allows_promotions": False,
        "opted_out": False,
        "is_active_relationship": False,
        "user_opens_biz_msgs": False,
        "user_dismisses_biz_msgs": False,
    }

    rel = data_store.get_user_business_rel(user_id, business_id)
    if not rel:
        return features

    features["has_relationship"] = True
    features["relationship_type"] = rel["why"]
    features["allows_promotions"] = rel["allows_promotions"]
    features["opted_out"] = rel["opted_out"]

    # Active relationship = recent activity + engagement
    features["is_active_relationship"] = rel["activity_count_180d"] >= 2

    # User opens or dismisses business messages
    if rel["msgs_opened_30d"] + rel["msgs_dismissed_30d"] > 0:
        open_rate = rel["msgs_opened_30d"] / (
            rel["msgs_opened_30d"] + rel["msgs_dismissed_30d"]
        )
        features["user_opens_biz_msgs"] = open_rate > 0.4
        features["user_dismisses_biz_msgs"] = open_rate <= 0.2

    return features


def compute_group_engagement_features(context):
    """Compute how the user engages with this group."""
    user_id = context.get("user_id", "")
    group_id = context.get("group_id", "")
    data_store = context["data_store"]

    features = {
        "is_member": False,
        "group_muted": False,
        "user_is_admin": False,
        "user_active_in_group": False,
        "user_high_dismiss_in_group": False,
        "group_type": None,
    }

    membership = data_store.get_membership(user_id, group_id)
    group_data = data_store.get_group(group_id)

    if group_data:
        features["group_type"] = group_data["group_type"]

    if not membership:
        return features

    features["is_member"] = True
    features["group_muted"] = membership["group_muted"]
    features["user_is_admin"] = membership["role"] == "admin"

    # Active = sends messages or replies
    features["user_active_in_group"] = (
        membership["messages_sent_30d"] >= 3 or
        membership["replies_sent_30d"] >= 1
    )

    # High dismiss rate in this group
    total_interactions = membership["messages_read_30d"] + membership["dismissed_30d"]
    if total_interactions > 0:
        features["user_high_dismiss_in_group"] = (
            membership["dismissed_30d"] / total_interactions > 0.5
        )

    return features


def compute_quiet_hours(context, created_at):
    """Check if message falls within user's DND window."""
    user_id = context.get("user_id", "")
    data_store = context["data_store"]
    user_data = data_store.get_user(user_id)

    if not user_data or not created_at:
        return {"in_quiet_hours": False}

    dnd = user_data.get("dnd_window", "")
    if not dnd:
        return {"in_quiet_hours": False}

    try:
        parts = dnd.split("-")
        start_h, start_m = map(int, parts[0].split(":"))
        end_h, end_m = map(int, parts[1].split(":"))

        # Parse message hour
        time_part = created_at.strip().split(" ")
        if len(time_part) >= 2:
            h, m = map(int, time_part[1].split(":"))
        else:
            return {"in_quiet_hours": False}

        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        msg_minutes = h * 60 + m

        if start_minutes > end_minutes:
            # Overnight window (e.g., 22:00-07:00)
            in_dnd = msg_minutes >= start_minutes or msg_minutes < end_minutes
        else:
            in_dnd = start_minutes <= msg_minutes < end_minutes

        return {"in_quiet_hours": in_dnd}
    except (ValueError, IndexError):
        return {"in_quiet_hours": False}


def compute_history_engagement(context):
    """
    Compute how the user has historically engaged with similar messages
    from this sender/business/group.
    """
    data_store = context["data_store"]
    user_id = context.get("user_id", "")
    sender_id = context.get("sender_user_id", "")
    business_id = context.get("business_id", "")
    group_id = context.get("group_id", "")

    # Get relevant historical messages
    if business_id:
        history = data_store.get_business_history(user_id, business_id)
    elif sender_id:
        history = data_store.get_sender_history(user_id, sender_id)
    else:
        history = []

    if not history:
        return {
            "has_history": False,
            "history_open_rate": 0.5,
            "history_dismiss_rate": 0.3,
            "history_report_count": 0,
            "mostly_opened": False,
            "mostly_dismissed": False,
            "previously_reported": False,
        }

    opened = 0
    replied = 0
    dismissed = 0
    reported = 0

    for h in history:
        ev = data_store.get_event(h["message_id"])
        if ev:
            if ev["opened"]:
                opened += 1
            if ev["replied"]:
                replied += 1
            if ev["dismissed"]:
                dismissed += 1
            if ev["reported"]:
                reported += 1

    total = opened + dismissed
    open_rate = opened / max(total, 1)
    dismiss_rate = dismissed / max(total, 1)

    return {
        "has_history": True,
        "history_count": len(history),
        "history_open_rate": open_rate,
        "history_dismiss_rate": dismiss_rate,
        "history_reply_count": replied,
        "history_report_count": reported,
        "mostly_opened": open_rate > 0.6,
        "mostly_dismissed": dismiss_rate > 0.5,
        "previously_reported": reported > 0,
    }


def compute_all_features(msg, context):
    """Compute all features for a message and return unified feature dict."""
    text = msg.get("message_text", "") or ""
    created_at = msg.get("created_at", "")

    text_features = compute_text_features(text)
    sender_features = compute_sender_features(context)
    user_engagement = compute_user_engagement(context)
    biz_features = compute_business_relationship_features(context)
    group_features = compute_group_engagement_features(context)
    quiet_hours = compute_quiet_hours(context, created_at)
    history_engagement = compute_history_engagement(context)

    return {
        "text": text_features,
        "sender": sender_features,
        "user": user_engagement,
        "business_rel": biz_features,
        "group": group_features,
        "quiet_hours": quiet_hours,
        "history": history_engagement,
    }
