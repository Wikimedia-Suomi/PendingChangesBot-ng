from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reviews.autoreview.runner import review_single_revision


class Command(BaseCommand):
    help = (
        "Review a single revision by its revision ID. "
        "Runs the full autoreview check pipeline and optionally submits the review."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("revid", type=int, help="The revision ID to review.")
        parser.add_argument(
            "--wiki",
            default="fi",
            help="Wiki code (e.g. 'fi', 'en'). Defaults to 'fi'.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            default=False,
            help="Actually submit the review (default is dry-run).",
        )
        parser.add_argument(
            "--no-log",
            action="store_true",
            default=False,
            help="Skip writing a BotActivity log entry.",
        )

    def handle(self, *args, **options):
        revid: int = options["revid"]
        wiki_code: str = options["wiki"]
        dry_run: bool = not options["live"]
        log_activity: bool = not options["no_log"]

        mode_label = "LIVE" if not dry_run else "DRY-RUN"
        self.stdout.write(f"Reviewing revision {revid} on {wiki_code} [{mode_label}]...")

        try:
            result = review_single_revision(
                revid=revid,
                wiki_code=wiki_code,
                log_activity=log_activity,
                dry_run=dry_run,
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        # Display check results
        self.stdout.write("")
        for test in result["tests"]:
            status_icon = {"ok": "✅", "warning": "⚠️", "fail": "❌"}.get(test["status"], "•")
            self.stdout.write(f"  {status_icon} {test['id']}: {test['status']} — {test['message']}")

        # Display decision
        decision = result["decision"]
        decision_style = {
            "approve": self.style.SUCCESS,
            "blocked": self.style.ERROR,
            "manual": self.style.WARNING,
        }.get(decision["status"], self.style.NOTICE)

        self.stdout.write("")
        self.stdout.write(
            decision_style(f"Decision: {decision['status'].upper()} — {decision['label']}")
        )
        self.stdout.write(f"  Reason: {decision['reason']}")
        self.stdout.write(f"  Duration: {result['total_duration_ms']:.1f} ms")

        if result["review_submitted"]:
            self.stdout.write(self.style.SUCCESS(f"  Review submitted: {result['review_message']}"))
        elif not dry_run and decision["status"] == "approve":
            self.stdout.write(self.style.ERROR(f"  Review failed: {result['review_message']}"))
