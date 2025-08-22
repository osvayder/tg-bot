from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

def parse_deadline(args: str, tz_name: str) -> datetime | None:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    a = args.strip()
    # Форматы: "YYYY-MM-DD HH:MM" | "YYYY-MM-DD" | "HH:MM"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(a, fmt).replace(tzinfo=tz)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59)
            return dt
        except ValueError:
            pass
    # только время HH:MM → сегодня, если прошло — завтра
    try:
        hh, mm = map(int, a.split(":"))
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    except Exception:
        return None