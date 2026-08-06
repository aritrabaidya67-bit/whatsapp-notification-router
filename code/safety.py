"""
Safety engine: detects scam, spam, prompt injection, and other risk signals.
Returns a risk assessment dict for each message context.
"""
import re
from config import (
    PROMPT_INJECTION_PATTERNS, OTP_SCAM_KEYWORDS,
    FINANCIAL_SCAM_KEYWORDS, URGENCY_PRESSURE_KEYWORDS,
    BUSINESS_REPORT_THRESHOLD, BUSINESS_AGE_SUSPICIOUS,
    FORWARD_CHAIN_KEYWORDS, HEALTH_FORWARD_KEYWORDS,
)


def _text_lower(text):
    """Safely lowercase text, handling None."""
    return (text or "").lower().strip()


def detect_prompt_injection(text):
    """Check if the message tries to manipulate the routing system."""
    t = _text_lower(text)
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.lower() in t:
            return True
    return False


def detect_otp_scam(text):
    """Check for OTP/verification phishing keywords."""
    t = _text_lower(text)
    score = 0
    for kw in OTP_SCAM_KEYWORDS:
        if kw.lower() in t:
            score += 1
    return score


def detect_financial_scam(text):
    """Check for financial scam indicators."""
    t = _text_lower(text)
    score = 0
    for kw in FINANCIAL_SCAM_KEYWORDS:
        if kw.lower() in t:
            score += 1
    return score


def detect_urgency_pressure(text):
    """Check for urgency pressure language (used in scams)."""
    t = _text_lower(text)
    score = 0
    for kw in URGENCY_PRESSURE_KEYWORDS:
        if kw.lower() in t:
            score += 1
    return score


def detect_suspicious_urls(text):
    """Check for suspicious URLs or domains in the text."""
    t = _text_lower(text)
    suspicious_patterns = [
        r'bit\.ly/', r'shorturl\.', r'tinyurl\.',
        r'account-login', r'account-help',
        r'pay-check-secure', r'-secure-alert',
        r'-kyc\.', r'-refund\.', r'-delivery\.',
        r'-rewards\.', r'-billpay\.', r'-simkyc\.',
        r'-gold\.', r'-helpdesk\.',
        r'lucky-draw', r'vl\.gl',
    ]
    score = 0
    for pat in suspicious_patterns:
        if re.search(pat, t):
            score += 1
    return score


def assess_business_risk(business_data):
    """Assess risk based on business account metadata."""
    if not business_data:
        return {"risk_level": "unknown", "risk_score": 0.3}

    risk_score = 0.0
    risk_reasons = []

    # Unverified business
    if not business_data["verified"]:
        risk_score += 0.3
        risk_reasons.append("unverified_business")

    # Domain mismatch
    if business_data["domain_mismatch"]:
        risk_score += 0.25
        risk_reasons.append("domain_mismatch")

    # High reports
    if business_data["reports_30d"] >= BUSINESS_REPORT_THRESHOLD:
        risk_score += 0.25
        risk_reasons.append("high_reports")

    # Very new account
    if business_data["account_age_days"] <= BUSINESS_AGE_SUSPICIOUS:
        risk_score += 0.15
        risk_reasons.append("new_account")

    # Very new sender domain
    if business_data["sender_domain_age"] <= 20:
        risk_score += 0.1
        risk_reasons.append("new_domain")

    # No official domain
    if not business_data["official_domain"]:
        risk_score += 0.1
        risk_reasons.append("no_official_domain")

    risk_level = "low"
    if risk_score >= 0.6:
        risk_level = "high"
    elif risk_score >= 0.3:
        risk_level = "medium"

    return {
        "risk_level": risk_level,
        "risk_score": min(risk_score, 1.0),
        "risk_reasons": risk_reasons,
    }


def assess_sender_risk(context):
    """Assess risk from the sender, considering user history."""
    risk_score = 0.0
    risk_flags = []

    # Check if user previously reported this sender/business history
    sender_history = context.get("sender_history", [])
    for hist_msg in sender_history:
        event = context.get("data_store").get_event(hist_msg["message_id"])
        if event and event.get("reported"):
            risk_score += 0.3
            risk_flags.append("previously_reported_sender")
            break

    # First message from unknown sender in personal chat
    if context.get("conversation_type", "") == "personal":
        if not sender_history and not context.get("business_data"):
            risk_score += 0.1
            risk_flags.append("unknown_sender")

    return {"risk_score": risk_score, "risk_flags": risk_flags}


def detect_forwarded_chain(text, forwarded_count):
    """Detect chain/forwarded messages with viral patterns."""
    t = _text_lower(text)
    is_chain = False
    chain_type = None

    if forwarded_count >= 5:
        is_chain = True

    # Check for chain keywords
    for kw in FORWARD_CHAIN_KEYWORDS:
        if kw.lower() in t:
            is_chain = True
            break

    # Health misinformation forwards
    for kw in HEALTH_FORWARD_KEYWORDS:
        if kw.lower() in t:
            is_chain = True
            chain_type = "health_forward"
            break

    if is_chain and not chain_type:
        chain_type = "chain_forward"

    return is_chain, chain_type


def full_risk_assessment(msg, context):
    """
    Complete risk assessment for a message.
    Returns dict with risk scores, flags, and whether it should be muted for safety.
    """
    text = msg.get("message_text", "") or ""
    forwarded = int(msg.get("forwarded_count", 0) or 0)

    # Prompt injection
    is_injection = detect_prompt_injection(text)

    # OTP/verification scam
    otp_score = detect_otp_scam(text)

    # Financial scam signals
    financial_score = detect_financial_scam(text)

    # Urgency pressure
    pressure_score = detect_urgency_pressure(text)

    # Suspicious URLs
    url_score = detect_suspicious_urls(text)

    # Business risk
    business_data = context.get("business_data")
    biz_risk = assess_business_risk(business_data)

    # Sender risk
    sender_risk = assess_sender_risk(context)

    # Forwarded chain
    is_chain, chain_type = detect_forwarded_chain(text, forwarded)

    # ─── Composite scam score ────────────────────────────────────────────
    scam_score = 0.0

    if is_injection:
        scam_score = 1.0  # Immediate scam flag

    if otp_score >= 2:
        scam_score = max(scam_score, 0.8)
    elif otp_score >= 1:
        scam_score = max(scam_score, 0.5)

    if financial_score >= 2:
        scam_score = max(scam_score, 0.7)
    elif financial_score >= 1:
        scam_score = max(scam_score, 0.4)

    # Business risk amplifies scam signals
    if biz_risk["risk_level"] == "high":
        scam_score = max(scam_score, 0.6)
        # If there's also OTP/financial signals with high-risk business
        if otp_score >= 1 or financial_score >= 1:
            scam_score = max(scam_score, 0.9)

    # Urgency pressure + other scam signals = stronger scam
    if pressure_score >= 1 and (otp_score >= 1 or financial_score >= 1):
        scam_score = max(scam_score, scam_score + 0.1)

    # Suspicious URL + other signals
    if url_score >= 1 and (otp_score >= 1 or financial_score >= 1 or
                            biz_risk["risk_level"] in ("high", "medium")):
        scam_score = max(scam_score, scam_score + 0.1)

    # Sender previously reported
    if "previously_reported_sender" in sender_risk.get("risk_flags", []):
        scam_score = max(scam_score, scam_score + 0.15)

    scam_score = min(scam_score, 1.0)

    # ─── Determine safety action ─────────────────────────────────────────
    should_mute = False
    safety_type = None
    safety_reason = None

    if scam_score >= 0.5:
        should_mute = True
        safety_type = "scam"
        if is_injection:
            safety_reason = "prompt_injection"
        elif otp_score >= 1:
            safety_reason = "otp_phishing"
        elif financial_score >= 1:
            safety_reason = "financial_scam"
        elif biz_risk["risk_level"] == "high":
            safety_reason = "suspicious_business"
        else:
            safety_reason = "combined_risk_signals"

    return {
        "scam_score": scam_score,
        "is_injection": is_injection,
        "otp_score": otp_score,
        "financial_score": financial_score,
        "pressure_score": pressure_score,
        "url_score": url_score,
        "business_risk": biz_risk,
        "sender_risk": sender_risk,
        "is_chain": is_chain,
        "chain_type": chain_type,
        "forwarded_count": forwarded,
        "should_mute": should_mute,
        "safety_type": safety_type,
        "safety_reason": safety_reason,
    }
