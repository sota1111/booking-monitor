#!/usr/bin/env python3
"""CLI to seed sample (mock) data for dashboard evaluation (SOT-1152).

Registers a handful of sample booking-monitor targets (writing a sample config)
and populates the history JSONL files so the dashboard can be evaluated without
live scraping.

Usage::

    python scripts/seed_sample_data.py            # seed config.sample.json + logs/
    python scripts/seed_sample_data.py --force    # overwrite the sample config too

The seeding is idempotent: real (non-sample) history records are preserved; only
sample-tagged records are regenerated.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from booking_monitor.sample_data import seed_all  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config.sample.json",
        help="Path to write the sample config (default: config.sample.json)",
    )
    parser.add_argument(
        "--history-dir",
        default="logs",
        help="Directory for the history JSONL files (default: logs)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the sample config even if it already exists",
    )
    args = parser.parse_args()

    summary = seed_all(
        config_path=args.config,
        history_dir=args.history_dir,
        force=args.force,
    )

    print("Sample data seeded:")
    print(f"  config file        : {args.config} ({summary['config_targets']} targets)")
    print(f"  latest states      : {summary['latest']}  -> {args.history_dir}/history.jsonl")
    print(f"  check history       : {summary['checks']}  -> {args.history_dir}/check_history.jsonl")
    print(
        f"  notification history: {summary['notifications']}  -> "
        f"{args.history_dir}/notification_history.jsonl"
    )
    print()
    print("Open the dashboard (SEED_SAMPLE_DATA=1) to evaluate the display.")


if __name__ == "__main__":
    main()
