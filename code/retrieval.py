"""
Historical evidence retrieval: selects relevant past messages as evidence.
"""
import re
from collections import Counter


def _text_lower(text):
    return (text or "").lower().strip()


def _extract_keywords(text):
    """Extract meaningful words from text (excluding stopwords)."""
    t = _text_lower(text)
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "can", "could", "must", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "during", "before", "after", "above", "below", "between", "under",
        "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
        "neither", "each", "every", "all", "any", "few", "more", "most",
        "other", "some", "such", "no", "only", "same", "than", "too", "very",
        "just", "because", "also", "that", "this", "these", "those", "it",
        "its", "i", "me", "my", "we", "our", "you", "your", "he", "his",
        "she", "her", "they", "them", "their", "what", "which", "who", "whom",
        "if", "when", "where", "how", "about", "up", "out", "off", "down",
        "then", "once", "here", "there", "why", "so", "please", "pls",
        "hi", "hello", "dear", "customer", "tap", "below", "view", "details",
        "reply", "stop", "unsubscribe", "team",
    }
    words = re.findall(r'[a-z]+', t)
    return [w for w in words if len(w) > 2 and w not in stopwords]


def _keyword_similarity(text1, text2):
    """Compute keyword overlap similarity between two texts."""
    kw1 = set(_extract_keywords(text1))
    kw2 = set(_extract_keywords(text2))
    if not kw1 or not kw2:
        return 0.0
    intersection = kw1 & kw2
    union = kw1 | kw2
    return len(intersection) / len(union)  # Jaccard similarity


def retrieve_evidence(msg, context, data_store, max_results=3):
    """
    Retrieve the most relevant historical message IDs as evidence.

    Strategy:
    1. Get history for same user
    2. Filter by same sender/business/group
    3. Score by textual similarity + recency + user reaction relevance
    4. Return top IDs

    Returns: list of evidence message_id strings, or ["none"]
    """
    user_id = msg.get("user_id", "")
    sender_id = msg.get("sender_user_id", "") or ""
    business_id = msg.get("business_id", "") or ""
    group_id = msg.get("group_id", "") or ""
    msg_text = msg.get("message_text", "") or ""

    candidates = []

    # Priority 1: Same sender (for personal/group messages)
    if sender_id:
        sender_hist = data_store.get_sender_history(user_id, sender_id)
        for h in sender_hist:
            candidates.append(("sender", h))

    # Priority 2: Same business
    if business_id:
        biz_hist = data_store.get_business_history(user_id, business_id)
        for h in biz_hist:
            candidates.append(("business", h))

    # Priority 3: Same group (if not already covered by sender)
    if group_id and not sender_id:
        grp_hist = data_store.get_group_history(user_id, group_id)
        for h in grp_hist[:10]:  # Limit group history
            candidates.append(("group", h))

    # If no candidates from direct relationships, try broader user history
    if not candidates:
        user_hist = data_store.get_user_history(user_id)
        for h in user_hist[:15]:
            candidates.append(("user", h))

    if not candidates:
        return ["none"]

    # ─── Score candidates ────────────────────────────────────────────────
    scored = []
    seen_ids = set()

    for source, hist_msg in candidates:
        mid = hist_msg["message_id"]
        if mid in seen_ids:
            continue
        seen_ids.add(mid)

        score = 0.0

        # Source priority
        if source == "sender":
            score += 0.3
        elif source == "business":
            score += 0.25
        elif source == "group":
            score += 0.1

        # Textual similarity
        hist_text = hist_msg.get("message_text", "") or ""
        sim = _keyword_similarity(msg_text, hist_text)
        score += sim * 0.4

        # Check user reaction (opened/replied = relevant evidence)
        event = data_store.get_event(mid)
        if event:
            if event["opened"] and event["replied"]:
                score += 0.15
            elif event["opened"]:
                score += 0.1
            elif event["dismissed"]:
                score += 0.1  # Dismissal is also relevant evidence
            if event["reported"]:
                score += 0.2  # Reported = very relevant for scam detection
            if event["muted_after"]:
                score += 0.1

        # Same conversation type match
        if hist_msg.get("conversation_type") == msg.get("conversation_type"):
            score += 0.05

        # Same group match
        if group_id and hist_msg.get("group_id") == group_id:
            score += 0.1

        # Same business match
        if business_id and hist_msg.get("business_id") == business_id:
            score += 0.1

        scored.append((score, mid))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    # Return top results
    result_ids = [mid for _, mid in scored[:max_results]]

    # Validate all IDs exist in history
    result_ids = [mid for mid in result_ids if data_store.is_valid_evidence_id(mid)]

    if not result_ids:
        return ["none"]

    return result_ids


def format_evidence_ids(evidence_list):
    """Format evidence IDs for output CSV."""
    if not evidence_list or evidence_list == ["none"]:
        return "none"
    return ";".join(evidence_list)
