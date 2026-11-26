"""Pure calendar/statistics logic; no Django dependency."""
from datetime import timedelta
from calendar import monthrange

DEFAULT_DURATION_DAYS = 40  # provisional product decision
MAX_DURATION_DAYS = 730


def scheduled_periods(start, duration, kind, rule):
    """Inclusive local dates, clipped to challenge bounds."""
    end = start + timedelta(days=duration - 1)
    cursor = start
    while cursor <= end:
        if kind == 'daily':
            if cursor.weekday() in rule['weekdays']:
                yield cursor, cursor, 1
            cursor += timedelta(days=1)
        else:
            if kind == 'weekly':  # Saturday–Friday
                last = cursor + timedelta(days=(4 - cursor.weekday()) % 7)
            else:
                last = cursor.replace(day=monthrange(cursor.year, cursor.month)[1])
            last = min(last, end)
            quota = min(rule['occurrences'], (last - cursor).days + 1)
            yield cursor, last, quota
            cursor = last + timedelta(days=1)


def successful(version, log):
    if version.goal_type == 'binary':
        return log.binary_value == version.binary_success
    if log.numeric_delta is None:
        return False
    if version.comparison == 'gte':
        return log.numeric_delta >= version.target_value
    return log.numeric_delta <= version.target_value


def week_key(day):
    return day - timedelta(days=(day.weekday() - 5) % 7)


def streak(rows, today):
    """Rows: (start, end, succeeded, policy, kind). Rest preserves but never increments."""
    current = best = 0
    used_rest = set()
    for start, end, ok, policy, kind in rows:
        if start > today:
            break
        if ok:
            current += 1
            best = max(best, current)
        elif end < today:
            key = week_key(start)
            if policy == 'flexible' and kind == 'daily' and current and key not in used_rest:
                used_rest.add(key)
            else:
                current = 0
    return current, best
