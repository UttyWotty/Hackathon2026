#!/usr/bin/env python3
"""
Token Usage Report Generator

Generate reports and analytics for LLM token usage across all services.

Usage:
    python token_usage_report.py --summary
    python token_usage_report.py --detailed --start-date 2024-10-01
    python token_usage_report.py --export report.xlsx
    python token_usage_report.py --last-days 7
"""

import argparse
from datetime import datetime, timedelta

import pandas as pd
from token_tracker import get_token_tracker


def print_summary(tracker):
    """Print summary report to console."""
    df = tracker.generate_report()

    if df.empty:
        print("\n❌ No usage data available.")
        return

    summary = tracker.get_cost_summary(df)

    print("\n" + "=" * 60)
    print("TOKEN USAGE SUMMARY")
    print("=" * 60)
    print(
        f"Date Range: {summary['date_range']['start'][:10]} to {summary['date_range']['end'][:10]}"
    )
    print(f"Total Requests: {summary['request_count']:,}")
    print(f"Total Tokens: {summary['total_tokens']:,}")
    print(f"  - Input: {summary['total_input_tokens']:,}")
    print(f"  - Output: {summary['total_output_tokens']:,}")
    print(f"Total Cost: ${summary['total_cost_usd']:.4f}")
    print(f"Avg Cost/Request: ${summary['avg_cost_per_request']:.6f}")

    print("\n" + "-" * 60)
    print("COST BY MODEL")
    print("-" * 60)
    for model, cost in sorted(
        summary["by_model"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {model}: ${cost:.4f}")

    print("\n" + "-" * 60)
    print("COST BY OPERATION")
    print("-" * 60)
    for operation, cost in sorted(
        summary["by_operation"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {operation}: ${cost:.4f}")

    print("=" * 60 + "\n")


def print_detailed(tracker, start_date=None, end_date=None):
    """Print detailed usage breakdown."""
    df = tracker.generate_report(start_date, end_date)

    if df.empty:
        print("\n❌ No usage data available for the specified date range.")
        return

    print("\n" + "=" * 80)
    print("DETAILED TOKEN USAGE")
    print("=" * 80)

    # Group by date
    df["date"] = df["timestamp"].dt.date
    daily = (
        df.groupby("date")
        .agg(
            {
                "input_tokens": "sum",
                "output_tokens": "sum",
                "total_tokens": "sum",
                "cost_usd": "sum",
                "model_id": "count",
            }
        )
        .rename(columns={"model_id": "requests"})
    )

    print(daily.to_string())
    print("=" * 80 + "\n")


def export_report(tracker, output_file):
    """Export usage data to Excel."""
    df = tracker.generate_report()

    if df.empty:
        print("\n❌ No usage data available to export.")
        return

    try:
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            # Raw data
            df.to_excel(writer, sheet_name="Raw Data", index=False)

            # Daily summary
            df["date"] = df["timestamp"].dt.date
            daily = (
                df.groupby("date")
                .agg(
                    {
                        "input_tokens": "sum",
                        "output_tokens": "sum",
                        "total_tokens": "sum",
                        "cost_usd": "sum",
                        "model_id": "count",
                    }
                )
                .rename(columns={"model_id": "requests"})
            )
            daily.to_excel(writer, sheet_name="Daily Summary")

            # By model
            by_model = (
                df.groupby("model_id")
                .agg(
                    {
                        "input_tokens": "sum",
                        "output_tokens": "sum",
                        "total_tokens": "sum",
                        "cost_usd": "sum",
                        "operation": "count",
                    }
                )
                .rename(columns={"operation": "requests"})
            )
            by_model.to_excel(writer, sheet_name="By Model")

            # By operation
            by_operation = (
                df.groupby("operation")
                .agg(
                    {
                        "input_tokens": "sum",
                        "output_tokens": "sum",
                        "total_tokens": "sum",
                        "cost_usd": "sum",
                        "model_id": "count",
                    }
                )
                .rename(columns={"model_id": "requests"})
            )
            by_operation.to_excel(writer, sheet_name="By Operation")

        print(f"\n✅ Report exported to: {output_file}")
    except Exception as e:
        print(f"\n❌ Error exporting report: {e}")


def main():
    """Main entry point for the report generator."""
    parser = argparse.ArgumentParser(
        description="Generate token usage reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python token_usage_report.py --summary
  python token_usage_report.py --detailed --last-days 7
  python token_usage_report.py --export monthly_report.xlsx
  python token_usage_report.py --start-date 2024-10-01 --end-date 2024-10-31
        """,
    )

    parser.add_argument("--summary", action="store_true", help="Print summary report")
    parser.add_argument("--detailed", action="store_true", help="Print detailed report")
    parser.add_argument(
        "--export", type=str, metavar="FILE", help="Export to Excel file"
    )
    parser.add_argument(
        "--start-date", type=str, metavar="YYYY-MM-DD", help="Start date"
    )
    parser.add_argument("--end-date", type=str, metavar="YYYY-MM-DD", help="End date")
    parser.add_argument("--last-days", type=int, metavar="N", help="Show last N days")

    args = parser.parse_args()

    tracker = get_token_tracker()

    # Calculate date range
    start_date = args.start_date
    end_date = args.end_date

    if args.last_days:
        end_date = datetime.now().isoformat()
        start_date = (datetime.now() - timedelta(days=args.last_days)).isoformat()

    # Generate reports
    if args.summary:
        print_summary(tracker)

    if args.detailed:
        print_detailed(tracker, start_date, end_date)

    if args.export:
        export_report(tracker, args.export)

    # Default: show summary
    if not any([args.summary, args.detailed, args.export]):
        print_summary(tracker)


if __name__ == "__main__":
    main()
