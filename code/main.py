"""
Main entry point: orchestrates the complete Message Notification Router pipeline.

Usage:
    python code/main.py
"""
import sys
import os
import csv
import time

# Ensure code/ is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataStore
from classifier import classify_message
from validator import validate_and_report
from evaluation import evaluate_on_samples
from config import OUTPUT_PATH, OUTPUT_COLUMNS, CACHE_DIR


def main():
    start_time = time.time()

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print("=" * 70)
    print("Message Notification Router - Pipeline Start")
    print("=" * 70)

    # --- Step 1: Load data -----------------------------------------------
    print("\n[1/5] Loading datasets...")
    data_store = DataStore()
    print(f"  [OK] Messages to predict: {len(data_store.messages)}")
    print(f"  [OK] Sample messages:     {len(data_store.sample_messages)}")
    print(f"  [OK] Users:               {len(data_store.users)}")
    print(f"  [OK] Groups:              {len(data_store.groups)}")
    print(f"  [OK] Businesses:          {len(data_store.businesses)}")
    print(f"  [OK] History messages:    {len(data_store.history_by_id)}")
    print(f"  [OK] Message events:      {len(data_store.events_by_message)}")
    print(f"  [OK] Images:              {len(data_store.images)}")
    print(f"  [OK] Voice notes:         {len(data_store.voice_notes)}")

    # --- Step 2: Evaluate on samples first -------------------------------
    print("\n[2/5] Evaluating on sample messages...")
    eval_results = evaluate_on_samples(data_store)

    # --- Step 3: Generate predictions for all messages -------------------
    print("\n[3/5] Generating predictions for all messages...")
    predictions = []
    for i, msg in enumerate(data_store.messages):
        pred = classify_message(msg, data_store)
        predictions.append(pred)
        if (i + 1) % 25 == 0:
            print(f"  Processed {i + 1}/{len(data_store.messages)} messages")

    print(f"  [OK] Generated {len(predictions)} predictions")

    # --- Step 4: Validate output -----------------------------------------
    print("\n[4/5] Validating output...")
    expected_ids = {msg["message_id"] for msg in data_store.messages}
    valid_evidence_ids = data_store.all_history_ids
    is_valid = validate_and_report(predictions, expected_ids, valid_evidence_ids)

    if not is_valid:
        print("[WARN] Validation failed - writing output anyway for debugging")

    # --- Step 5: Write output.csv ----------------------------------------
    print("\n[5/5] Writing output.csv...")
    write_output(predictions, OUTPUT_PATH)
    print(f"  [OK] Written to {OUTPUT_PATH}")

    # ─── Summary ─────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"Pipeline complete in {elapsed:.1f}s")
    print(f"{'='*70}")

    # Distribution summary
    action_dist = {}
    type_dist = {}
    for p in predictions:
        action_dist[p["action"]] = action_dist.get(p["action"], 0) + 1
        type_dist[p["message_type"]] = type_dist.get(p["message_type"], 0) + 1

    print(f"\nAction distribution:")
    for a in sorted(action_dist.keys()):
        print(f"  {a}: {action_dist[a]}")

    print(f"\nMessage type distribution:")
    for t in sorted(type_dist.keys()):
        print(f"  {t}: {type_dist[t]}")

    # Confidence stats
    confidences = [p["confidence"] for p in predictions]
    print(f"\nConfidence stats:")
    print(f"  Mean: {sum(confidences)/len(confidences):.3f}")
    print(f"  Min:  {min(confidences):.3f}")
    print(f"  Max:  {max(confidences):.3f}")

    print(f"\nSample evaluation summary:")
    print(f"  Action accuracy:  {eval_results['action_accuracy']*100:.1f}%")
    print(f"  Type accuracy:    {eval_results['type_accuracy']*100:.1f}%")
    print(f"  Joint accuracy:   {eval_results['joint_accuracy']*100:.1f}%")

    return predictions


def write_output(predictions, output_path):
    """Write predictions to output.csv in the exact required format."""
    # Read the original output.csv to preserve message_id order
    original_order = []
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            original_order.append(row["message_id"])

    # Index predictions
    pred_index = {p["message_id"]: p for p in predictions}

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for msg_id in original_order:
            pred = pred_index.get(msg_id)
            if pred:
                writer.writerow({
                    "message_id": pred["message_id"],
                    "action": pred["action"],
                    "message_type": pred["message_type"],
                    "reason": pred["reason"],
                    "confidence": pred["confidence"],
                    "evidence_message_ids": pred["evidence_message_ids"],
                })
            else:
                # Fallback: this should never happen
                writer.writerow({
                    "message_id": msg_id,
                    "action": "digest",
                    "message_type": "unknown",
                    "reason": "Insufficient data for classification.",
                    "confidence": 0.5,
                    "evidence_message_ids": "none",
                })


if __name__ == "__main__":
    main()
