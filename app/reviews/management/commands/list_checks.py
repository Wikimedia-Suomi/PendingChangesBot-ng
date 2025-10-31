from django.core.management.base import BaseCommand

from reviews.autoreview.checks import AVAILABLE_CHECKS


class Command(BaseCommand):
    help = "List all available autoreview checks"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("\nAvailable Autoreview Checks:\n"))

        for check in sorted(AVAILABLE_CHECKS, key=lambda c: c["priority"]):
            line = (
                f"  {check['priority']:2d}. [{check['type']:9s}] "
                f"{check['id']:35s} - {check['name']}"
            )
            self.stdout.write(line)

        self.stdout.write(
            self.style.WARNING(
                "\nTo configure which checks run for a wiki, update the 'enabled_checks' "
                "field in WikiConfiguration.\n"
                "Leave it empty/null to run all checks (default behavior).\n"
            )
        )
