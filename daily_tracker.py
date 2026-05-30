"""
Daily usage tracker - stores snapshots of monthly usage
and calculates daily delta (today's consumption) and 7-day history.
"""
import json
import os
from datetime import datetime, date

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "daily_snapshots.json")


def load_snapshots():
    """Load snapshot history from disk."""
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_snapshots(snapshots):
    """Save snapshot history to disk."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(snapshots, f, indent=2)


def take_snapshot(usage_data):
    """
    usage_data: dict with {total_tokens, input_tokens, output_tokens, cache_hit_rate, monthly_cost}
    Returns today's delta and updated 7-day history.
    """
    today = date.today().isoformat()
    now_ts = datetime.now().isoformat()
    snapshots = load_snapshots()

    current = {
        "ts": now_ts,
        "total_tokens": usage_data.get("total_tokens", 0),
        "input_tokens": usage_data.get("input_tokens", 0),
        "output_tokens": usage_data.get("output_tokens", 0),
        "monthly_cost": float(usage_data.get("monthly_cost", 0)),
    }

    # Calculate today's delta
    today_delta = {"date": today, "tokens": 0, "input": 0, "output": 0, "cost": 0.0}

    if today in snapshots:
        prev = snapshots[today]
        # Check if there's a "baseline" (first snapshot of the day)
        baseline = prev.get("baseline", prev)
        today_delta["tokens"] = max(0, current["total_tokens"] - baseline.get("total_tokens", 0))
        today_delta["input"] = max(0, current["input_tokens"] - baseline.get("input_tokens", 0))
        today_delta["output"] = max(0, current["output_tokens"] - baseline.get("output_tokens", 0))
        today_delta["cost"] = round(max(0, current["monthly_cost"] - baseline.get("monthly_cost", 0)), 4)

        # Update last value
        snapshots[today]["last"] = current
    else:
        # First snapshot of the day
        snapshots[today] = {"baseline": current, "last": current}

    # Build 7-day history for bar chart
    seven_days = []
    for i in range(6, -1, -1):
        d = date.today()
        # Calculate date i days ago
        from datetime import timedelta
        day = (d - timedelta(days=i)).isoformat()

        if day in snapshots:
            s = snapshots[day]
            b = s.get("baseline", s.get("last", {}))
            l = s.get("last", b)
            seven_days.append({
                "date": day,
                "tokens": max(0, l.get("total_tokens", 0) - b.get("total_tokens", 0)),
                "input": max(0, l.get("input_tokens", 0) - b.get("input_tokens", 0)),
                "output": max(0, l.get("output_tokens", 0) - b.get("output_tokens", 0)),
                "cost": round(max(0, l.get("monthly_cost", 0) - b.get("monthly_cost", 0)), 4),
            })
        else:
            seven_days.append({"date": day, "tokens": 0, "input": 0, "output": 0, "cost": 0})

    # Clean up old entries (>30 days)
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    snapshots = {k: v for k, v in snapshots.items() if k >= cutoff}

    save_snapshots(snapshots)

    return {
        "today": today_delta,
        "seven_days": seven_days,
    }
