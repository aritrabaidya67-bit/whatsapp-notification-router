"""
Evaluation entry point.
Usage:
    python code/evaluation/main.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import DataStore
from evaluation import evaluate_on_samples


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("Loading datasets for evaluation...")
    data_store = DataStore()
    evaluate_on_samples(data_store)


if __name__ == "__main__":
    main()
