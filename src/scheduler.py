import time
import traceback
from datetime import datetime

from .config import get_settings
from .main import main as run_once


def run_scheduler():
    s = get_settings()
    interval_hours = int(
        getattr(s, "upload_interval_hours", None)
        or int(__import__("os").getenv("UPLOAD_INTERVAL_HOURS", "15"))
    )

    interval_seconds = interval_hours * 60 * 60

    print("🕒 StreamFlare Scheduler Started")
    print(f"⏱ Upload interval: {interval_hours} hours")
    print("🚀 Waiting for first run...\n")

    while True:
        start = datetime.utcnow()
        print(f"▶️ Run started at {start.isoformat()}Z")

        try:
            run_once()
            print("✅ Run completed successfully")
        except Exception as e:
            print("❌ Run failed:")
            traceback.print_exc()

        end = datetime.utcnow()
        elapsed = (end - start).total_seconds()

        sleep_for = max(interval_seconds - elapsed, 60)

        print(f"🕒 Next run in {sleep_for / 3600:.2f} hours\n")
        time.sleep(sleep_for)
