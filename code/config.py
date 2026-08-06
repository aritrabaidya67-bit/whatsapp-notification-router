"""
Configuration constants for the Message Notification Router.
"""
import os

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MEDIA_DIR = os.path.join(DATASET_DIR, "media")
IMAGES_DIR = os.path.join(MEDIA_DIR, "images")
AUDIO_DIR = os.path.join(MEDIA_DIR, "audio")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
OUTPUT_PATH = os.path.join(DATASET_DIR, "output.csv")

# ─── Allowed Values ──────────────────────────────────────────────────────────
VALID_ACTIONS = {"notify", "digest", "mute"}
VALID_MESSAGE_TYPES = {
    "personal", "urgent", "event", "payment", "business_update",
    "promotion", "greeting", "forward", "spam", "scam", "unknown"
}

OUTPUT_COLUMNS = [
    "message_id", "action", "message_type", "reason",
    "confidence", "evidence_message_ids"
]

# ─── Scam / Safety Keywords ─────────────────────────────────────────────────
PROMPT_INJECTION_PATTERNS = [
    "ignore all previous",
    "ignore previous routing",
    "routing override",
    "system note for the notification router",
    "system note for notification router",
    "internal router metadata",
    "assistant instruction",
    "set action=notify",
    "mark this as notify",
    "mark as notify",
    "action=notify",
    "confidence=1",
    "verified_business=true",
    "user_priority=high",
    "always mark this",
    "ignore sender risk",
]

OTP_SCAM_KEYWORDS = [
    "otp", "verification code", "login code", "6 digit",
    "share otp", "share the otp", "batao otp", "otp batao",
    "otp abhi", "otp leak", "otp verify", "verification failed",
    "send the code", "reply with the", "confirm your pin",
    "confirm pin", "account block", "account blocked",
    "profile will be restricted", "profile blocked",
    "profile ban", "account closure", "account lock",
    "permanently block", "profile band", "block ho jayega",
]

FINANCIAL_SCAM_KEYWORDS = [
    "bank details", "card details", "wallet details",
    "processing fee", "reattempt charge", "reattempt fee",
    "clearance amount", "pending charge", "verify wallet",
    "account-login", "account-help", "pay-check-secure",
    "-secure-alert", "-kyc", "-refund", "-delivery.in",
    "-rewards.in", "-billpay", "-simkyc", "-gold.in",
    "-helpdesk.in", "lucky-draw", "bit.ly/verify",
]

URGENCY_PRESSURE_KEYWORDS = [
    "immediately", "right now", "abhi", "jaldi",
    "before midnight", "expires today", "today only",
    "final reminder", "last chance", "don't delay",
    "otherwise your access", "warna", "restricted unless",
    "blocked tomorrow", "block ho jayega", "time kam hai",
]

GREETING_KEYWORDS = [
    "good morning", "blessed day", "stay positive",
    "share positivity", "share blessings", "send this to",
    "forward to", "forward this to", "share with",
    "sabka bhala kare", "positive energy failao",
    "keep smiling", "sabko", "bhagwan",
    "for blessings", "for good luck",
    "good evening", "good night",
    "have a blessed", "have a peaceful",
    "sending good vibes", "jai shri",
]

FORWARD_CHAIN_KEYWORDS = [
    "forward to at least", "share in all",
    "don't break the chain", "send to all",
    "forward in case", "fwd as received",
    "forwarding because", "share with elders",
    "share in family groups", "share with everyone",
    "share to all", "do not ignore",
]

HEALTH_FORWARD_KEYWORDS = [
    "health secret", "doctors don't tell",
    "herbal mix", "one habit will fix",
    "drink warm water", "drink ajwain",
    "stop all tablets", "ancient remedy",
]

PROMOTIONAL_KEYWORDS = [
    "% off", "discount", "cashback", "coupon",
    "limited time", "offer expires", "shop now",
    "reply stop to unsubscribe", "reply stop to opt out",
    "tap below to view", "t&c apply",
    "launch price", "welcome offer", "first order",
]

URGENCY_LEGITIMATE_KEYWORDS = [
    "call me now", "call me urgently",
    "can you call", "need literally",
    "please move", "in 10 min",
    "leaving in", "in the next 10 minutes",
    "before 5:15", "tow to", "expires today",
    "closes at 5 pm", "submit before",
    "pickup today", "moved to",
    "can you join", "prod review",
    "incident bridge", "escalation starts",
    "retry count crossed", "alert threshold",
    "rollback is approved", "stay online",
    "stay near laptop", "come online",
    "before end of day",
    "immediately after", "critical issue",
]

EVENT_KEYWORDS = [
    "field trip", "circular", "appointment",
    "pickup", "delivery", "return pickup",
    "scheduled", "booked", "reservation",
    "meeting", "standup", "review",
    "maintenance", "alarm test", "lift",
    "tanker", "water pressure", "gate",
    "bus is leaving", "bus list closes",
    "form is open", "register", "registration",
    "consent", "notice", "cultural",
    "fest", "walkathon", "deadline",
    "timing", "schedule", "reminder",
    "rescheduled", "cancelled", "postponed",
    "water supply", "power cut", "electricity",
    "pest control", "fumigation", "parking",
    "elevator", "intercom", "security",
    "society notice", "school notice",
]

PAYMENT_KEYWORDS = [
    "payment due", "maintenance payment",
    "receipt", "order ending", "packed",
    "delivery", "refund", "invoice",
    "statement is ready", "amount due",
]

# ─── Suspicious Domain Indicators ────────────────────────────────────────────
# Domains that don't match the official domain of the brand
SUSPICIOUS_DOMAIN_SUFFIXES = [
    "-delivery.in", "-refund.in", "-refund.com", "-kyc.in",
    "-rewards.in", "-billpay.in", "-simkyc.in", "-gold.in",
    "-helpdesk.in", "-secure-alert.com", "-alerts.net",
    "-payouts.com", "-simverify.com",
    "lucky-draw-result.in", "shorturl.at", "vl.gl",
    "weurl.co", "link.wame.pro",
]

# ─── Thresholds ──────────────────────────────────────────────────────────────
BUSINESS_REPORT_THRESHOLD = 15  # reports_30d above this → high risk
BUSINESS_AGE_SUSPICIOUS = 36    # account_age_days below this → new/suspicious
FORWARDED_CHAIN_THRESHOLD = 5   # forwarded_count above this → chain message
HIGH_DISMISSAL_RATE = 0.6       # user dismissal ratio above this → likely mute

# ─── Confidence Ranges ───────────────────────────────────────────────────────
CONF_HIGH = (0.85, 0.92)
CONF_MEDIUM = (0.78, 0.84)
CONF_LOW = (0.70, 0.78)
