"""
Evaluation harness: measures prediction quality against sample_messages.csv.
"""
import sys
import os
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataStore
from classifier import classify_message


def evaluate_on_samples(data_store, predictions=None):
    """
    Evaluate predictions against the 30 solved sample messages.

    If predictions is None, runs the classifier on sample messages.
    """
    samples = data_store.sample_messages

    if predictions is None:
        # Generate predictions for sample messages
        predictions = {}
        for sm in samples:
            pred = classify_message(sm, data_store)
            predictions[sm["message_id"]] = pred

    # Get ground truth
    ground_truth = data_store.sample_labels

    # ─── Metrics ─────────────────────────────────────────────────────────
    total = 0
    action_correct = 0
    type_correct = 0
    joint_correct = 0

    action_confusion = defaultdict(Counter)  # true → predicted
    type_confusion = defaultdict(Counter)

    confidence_errors = []

    for msg_id, truth in ground_truth.items():
        pred = predictions.get(msg_id)
        if not pred:
            continue

        total += 1
        true_action = truth["action"]
        true_type = truth["message_type"]
        pred_action = pred["action"]
        pred_type = pred["message_type"]

        # Action accuracy
        if pred_action == true_action:
            action_correct += 1
        action_confusion[true_action][pred_action] += 1

        # Type accuracy
        if pred_type == true_type:
            type_correct += 1
        type_confusion[true_type][pred_type] += 1

        # Joint accuracy
        if pred_action == true_action and pred_type == true_type:
            joint_correct += 1

        # Confidence error
        confidence_errors.append(abs(pred["confidence"] - truth["confidence"]))

    # ─── Print Results ───────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("SAMPLE EVALUATION RESULTS")
    print(f"{'='*70}")
    print(f"Total samples evaluated: {total}")
    print(f"Action accuracy:    {action_correct}/{total} = {action_correct/max(total,1)*100:.1f}%")
    print(f"Type accuracy:      {type_correct}/{total} = {type_correct/max(total,1)*100:.1f}%")
    print(f"Joint accuracy:     {joint_correct}/{total} = {joint_correct/max(total,1)*100:.1f}%")

    if confidence_errors:
        avg_conf_err = sum(confidence_errors) / len(confidence_errors)
        print(f"Avg confidence MAE: {avg_conf_err:.3f}")

    # ─── Action Confusion Matrix ─────────────────────────────────────────
    print(f"\n--- Action Confusion Matrix ---")
    actions = ["notify", "digest", "mute"]
    print(f"{'True/Pred':<12}", end="")
    for a in actions:
        print(f"{a:>10}", end="")
    print()
    for true_a in actions:
        print(f"{true_a:<12}", end="")
        for pred_a in actions:
            print(f"{action_confusion[true_a][pred_a]:>10}", end="")
        print()

    # ─── Per-Sample Details ──────────────────────────────────────────────
    print(f"\n--- Per-Sample Details ---")
    wrong_count = 0
    for msg_id, truth in sorted(ground_truth.items()):
        pred = predictions.get(msg_id)
        if not pred:
            continue

        true_a = truth["action"]
        true_t = truth["message_type"]
        pred_a = pred["action"]
        pred_t = pred["message_type"]

        if pred_a != true_a or pred_t != true_t:
            wrong_count += 1
            marker = "[X]"
            print(f"  {marker} {msg_id}: "
                  f"TRUE={true_a}/{true_t} -> "
                  f"PRED={pred_a}/{pred_t} "
                  f"[conf: {pred['confidence']:.2f} vs {truth['confidence']:.2f}]")

    if wrong_count == 0:
        print("  [PASS] All predictions correct!")

    print(f"\n{'='*70}\n")

    return {
        "total": total,
        "action_correct": action_correct,
        "type_correct": type_correct,
        "joint_correct": joint_correct,
        "action_accuracy": action_correct / max(total, 1),
        "type_accuracy": type_correct / max(total, 1),
        "joint_accuracy": joint_correct / max(total, 1),
        "avg_confidence_mae": sum(confidence_errors) / max(len(confidence_errors), 1),
    }


if __name__ == "__main__":
    print("Loading data...")
    ds = DataStore()
    print(f"Loaded {len(ds.messages)} messages, {len(ds.sample_messages)} samples")
    evaluate_on_samples(ds)
