"""
PendingChangesBot Background Runner

This script runs the bot in the background, checking for pending changes
and performing auto-reviews based on configured rules.
"""

import os
import sys
import time
from pathlib import Path

import django

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reviewer.settings")
django.setup()

from django.utils import timezone  # noqa: E402

from bot_control.models import BotStatus  # noqa: E402


def log(message):
    """Print timestamped log message"""
    timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message, flush=True)

    # Also write to log file
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "bot_runner.log"
    with open(log_file, "a") as f:
        f.write(log_message + "\n")


def should_continue():
    """Check if the bot should continue running"""
    try:
        status = BotStatus.get_current_status()
        return status.is_running
    except Exception as e:
        log(f"Error checking status: {e}")
        return False


def update_last_activity():
    """Update the last activity timestamp"""
    try:
        status = BotStatus.get_current_status()
        status.last_activity = timezone.now()
        status.save()
    except Exception as e:
        log(f"Error updating activity: {e}")


def perform_review_cycle():
    """
    Main review cycle - this is where the actual bot logic will go.
    For now, it's a placeholder.
    """
    # TODO: Implement actual review logic
    # This will:
    # 1. Query FlaggedRevs for pending changes
    # 2. Check each pending change against rules
    # 3. Auto-review if it passes checks
    # 4. Log the action

    log("Checking for pending changes... (TODO: implement actual logic)")
    time.sleep(5)  # Simulate some work


def run_bot():
    """Main bot loop"""
    log("=" * 60)
    log("PendingChangesBot started!")
    log("=" * 60)

    cycle_count = 0

    try:
        while should_continue():
            cycle_count += 1
            log(f"Starting review cycle #{cycle_count}")

            try:
                perform_review_cycle()
                update_last_activity()
                log(f"Cycle #{cycle_count} completed successfully")
            except Exception as e:
                log(f"Error in review cycle: {e}")
                # Update status with error
                try:
                    status = BotStatus.get_current_status()
                    status.error_message = str(e)
                    status.save()
                except Exception:  # noqa: S110
                    pass  # Ignore errors when updating status

            # Wait before next cycle (30 seconds)
            log("Waiting 30 seconds before next cycle...")
            for _ in range(30):
                if not should_continue():
                    break
                time.sleep(1)

        log("Bot stop signal received")

    except KeyboardInterrupt:
        log("Bot interrupted by user (Ctrl+C)")
    except Exception as e:
        log(f"Fatal error: {e}")
        # Update status with error
        try:
            status = BotStatus.get_current_status()
            status.error_message = str(e)
            status.is_running = False
            status.stopped_at = timezone.now()
            status.save()
        except Exception:  # noqa: S110
            pass  # Ignore errors when updating status
    finally:
        log("=" * 60)
        log("PendingChangesBot stopped!")
        log("=" * 60)


if __name__ == "__main__":
    run_bot()
