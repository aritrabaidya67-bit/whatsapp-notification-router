"""
Output validator: ensures output.csv conforms exactly to the competition contract.
"""
from config import VALID_ACTIONS, VALID_MESSAGE_TYPES, OUTPUT_COLUMNS


def validate_predictions(predictions, expected_message_ids, valid_evidence_ids):
    """
    Validate predictions against the competition contract.

    Args:
        predictions: list of prediction dicts
        expected_message_ids: set of message_ids from messages.csv
        valid_evidence_ids: set of valid historical message IDs

    Returns:
        (is_valid, errors) tuple
    """
    errors = []

    # Check we have predictions
    if not predictions:
        errors.append("ERROR: No predictions generated")
        return False, errors

    pred_ids = set()

    for i, pred in enumerate(predictions):
        row_label = f"Row {i+1} ({pred.get('message_id', 'MISSING')})"

        # Required columns present
        for col in OUTPUT_COLUMNS:
            if col not in pred:
                errors.append(f"{row_label}: Missing column '{col}'")

        msg_id = pred.get("message_id", "")
        action = pred.get("action", "")
        msg_type = pred.get("message_type", "")
        reason = pred.get("reason", "")
        confidence = pred.get("confidence", "")
        evidence = pred.get("evidence_message_ids", "")

        # message_id present
        if not msg_id:
            errors.append(f"{row_label}: Empty message_id")

        # No duplicates
        if msg_id in pred_ids:
            errors.append(f"{row_label}: Duplicate message_id '{msg_id}'")
        pred_ids.add(msg_id)

        # Valid action
        if action not in VALID_ACTIONS:
            errors.append(f"{row_label}: Invalid action '{action}'")

        # Valid message_type
        if msg_type not in VALID_MESSAGE_TYPES:
            errors.append(f"{row_label}: Invalid message_type '{msg_type}'")

        # Reason non-empty
        if not reason or not reason.strip():
            errors.append(f"{row_label}: Empty reason")

        # Confidence numeric and in [0, 1]
        try:
            conf_val = float(confidence)
            if conf_val < 0 or conf_val > 1:
                errors.append(f"{row_label}: Confidence {conf_val} not in [0, 1]")
        except (ValueError, TypeError):
            errors.append(f"{row_label}: Confidence '{confidence}' is not numeric")

        # Evidence format
        if evidence and evidence != "none":
            ev_ids = evidence.split(";")
            for ev_id in ev_ids:
                ev_id = ev_id.strip()
                if ev_id and ev_id not in valid_evidence_ids:
                    errors.append(f"{row_label}: Evidence ID '{ev_id}' not in history")

    # Check exact coverage
    missing = expected_message_ids - pred_ids
    extra = pred_ids - expected_message_ids

    if missing:
        errors.append(f"Missing message_ids: {sorted(missing)}")

    if extra:
        errors.append(f"Extra message_ids: {sorted(extra)}")

    # Row count
    if len(predictions) != len(expected_message_ids):
        errors.append(
            f"Row count mismatch: {len(predictions)} predictions vs "
            f"{len(expected_message_ids)} expected"
        )

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_and_report(predictions, expected_message_ids, valid_evidence_ids):
    """Validate and print a human-readable report."""
    is_valid, errors = validate_predictions(
        predictions, expected_message_ids, valid_evidence_ids
    )

    if is_valid:
        print(f"\n{'='*60}")
        print("[PASS] OUTPUT VALIDATION PASSED")
        print(f"   {len(predictions)} predictions, all valid")
        print(f"{'='*60}\n")
    else:
        print(f"\n{'='*60}")
        print(f"[FAIL] OUTPUT VALIDATION FAILED ({len(errors)} errors)")
        print(f"{'='*60}")
        for err in errors[:20]:
            print(f"  [WARN] {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")
        print()

    return is_valid
