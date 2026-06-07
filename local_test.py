"""
Run the analyst engine straight from the terminal, no Webex needed.

  ANTHROPIC_API_KEY=...  python local_test.py "top 5 HPE Aruba news this week in campus networking"

Use this to confirm the skill-aligned hunt works before wiring up the webhook.
"""

import sys
import datetime

from dotenv import load_dotenv

load_dotenv()  # pick up keys from .env

from analyst import run_analysis


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = "top 5 HPE Aruba news this week in campus networking"
    print(f"QUERY: {query}\n{'=' * 60}\n")
    out = run_analysis(query, today=datetime.date.today().isoformat())
    print(out)


if __name__ == "__main__":
    main()
