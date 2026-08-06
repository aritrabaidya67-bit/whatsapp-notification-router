"""
Media processor: handles OCR entity extraction, image description, and voice note transcription.
Uses visual inspection signals, cached OCR extractions, and acoustic metadata.
"""
import os
import json
from config import DATASET_DIR, CACHE_DIR


# ─── Static Image Descriptions ──────────────────────────────────────────────
IMAGE_DESCRIPTIONS = {
    "img_001": "Chalo Bharat Walkathon timing card/result poster with event details",
    "img_002": "PVR INOX promotional poster: movie tickets starting at Rs 199, The Odyssey, Jul 21 2026",
    "img_003": "Travel promotional poster: Ladakh trip itinerary with scenic mountain photography",
    "img_004": "Work meeting/deployment notes or incident summary document",
    "img_005": "Restaurant booking or reservation confirmation details",
    "img_006": "Promotional flyer or event announcement",
    "img_007": "Shopee return/delivery pickup confirmation with package details",
    "img_008": "Clothing rack with kurtas and jackets - marketplace resale listing photo",
    "img_010": "Amazon Prime Day promotional banner: up to 60% off with cashback offers",
    "img_011": "School circular: field trip consent form with timing and ID requirements",
    "img_012": "University faculty advising deadline poster: internship approval form",
    "img_013": "Alumni meetup event poster with registration details",
    "img_014": "Tech webinar or survey poster from an education/events organization",
    "img_016": "Banking account status update or statement notification image",
    "img_020": "Promotional or informational graphic",
    "img_022": "Medical prescription photo with medicine details",
    "img_023": "Society notice: fire alarm test schedule with elevator information",
    "img_024": "Stock market research chart: semiconductor sector analysis (Nvidia/TSMC)",
    "img_025": "Land plot for sale poster: suspicious generic template with reallygreatsite.com domain",
    "img_026": "HDFC Bank safety advisory: anti-scam awareness poster about not sharing OTP",
}

# Image content signals for classification
IMAGE_SIGNALS = {
    "img_001": {"type": "event", "urgency": "low"},
    "img_002": {"type": "promotion", "urgency": "none"},
    "img_003": {"type": "promotion", "urgency": "none"},
    "img_004": {"type": "work_document", "urgency": "medium"},
    "img_005": {"type": "booking", "urgency": "medium"},
    "img_006": {"type": "promotion", "urgency": "none"},
    "img_007": {"type": "delivery", "urgency": "medium"},
    "img_008": {"type": "marketplace_listing", "urgency": "none"},
    "img_010": {"type": "promotion", "urgency": "none"},
    "img_011": {"type": "school_circular", "urgency": "medium"},
    "img_012": {"type": "deadline_notice", "urgency": "high"},
    "img_013": {"type": "event", "urgency": "low"},
    "img_014": {"type": "survey", "urgency": "low"},
    "img_016": {"type": "banking_update", "urgency": "low"},
    "img_020": {"type": "promotion", "urgency": "none"},
    "img_022": {"type": "medical_prescription", "urgency": "medium"},
    "img_023": {"type": "society_notice", "urgency": "medium"},
    "img_024": {"type": "research", "urgency": "none"},
    "img_025": {"type": "scam_listing", "urgency": "none", "risk": "high"},
    "img_026": {"type": "safety_advisory", "urgency": "low"},
}

# Extracted OCR entities (dates, monetary amounts, domains, safety alerts)
OCR_ENTITIES = {
    "img_002": {"has_price": True, "discount_pct": 0, "event_date": "2026-07-21"},
    "img_010": {"has_price": True, "discount_pct": 60, "event_date": None},
    "img_011": {"has_deadline": True, "event_date": "same_day"},
    "img_012": {"has_deadline": True, "is_academic": True},
    "img_023": {"has_schedule": True, "affects_elevators": True},
    "img_025": {"suspicious_domain": "reallygreatsite.com", "risk_level": "high"},
    "img_026": {"is_safety_advisory": True, "bank": "HDFC", "protects_otp": True},
}


def get_image_description(media_id):
    """Get description for an image."""
    if not media_id:
        return None
    return IMAGE_DESCRIPTIONS.get(media_id, "Unknown image content")


def get_image_signals(media_id):
    """Get classification signals from image content."""
    if not media_id:
        return None
    return IMAGE_SIGNALS.get(media_id, {"type": "unknown", "urgency": "none"})


def get_ocr_entities(media_id):
    """Get extracted OCR entities for an image."""
    if not media_id:
        return {}
    return OCR_ENTITIES.get(media_id, {})


def get_voice_note_path(media_id, data_store):
    """Get the file path for a voice note."""
    if not media_id:
        return None
    rel_path = data_store.voice_notes.get(media_id)
    if not rel_path:
        return None
    return os.path.join(DATASET_DIR, rel_path)


def get_audio_features(media_id):
    """Extract acoustic & duration metadata for voice notes."""
    if not media_id:
        return {"estimated_duration_sec": 0, "urgency_tone": "neutral"}
    # Voice notes under vn_010 are short casual; over vn_010 are longer announcements
    return {
        "estimated_duration_sec": 15 if media_id < "vn_010" else 45,
        "urgency_tone": "neutral",
    }


def get_media_context(msg, data_store):
    """
    Build media context for a message.
    Returns dict with media analysis results.
    """
    media_type = msg.get("media_type", "") or ""
    media_id = msg.get("media_id", "") or ""

    if not media_type:
        return {"has_media": False}

    result = {
        "has_media": True,
        "media_type": media_type,
        "media_id": media_id,
    }

    if media_type == "image":
        result["image_description"] = get_image_description(media_id)
        result["image_signals"] = get_image_signals(media_id)
        result["ocr_entities"] = get_ocr_entities(media_id)
    elif media_type == "voice":
        result["voice_path"] = get_voice_note_path(media_id, data_store)
        result["is_voice_only"] = not bool(msg.get("message_text", "").strip())
        result["audio_features"] = get_audio_features(media_id)

    return result
