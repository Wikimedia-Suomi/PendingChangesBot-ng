from django.core.management.base import BaseCommand, CommandError
from reviews.autoreview.checks import AVAILABLE_CHECKS
from reviews.models import Wiki, WikiConfiguration


class Command(BaseCommand):
    help = "Configure which autoreview checks are enabled for a wiki"

    def add_arguments(self, parser):
        parser.add_argument("wiki_code", type=str, help="Wiki code (e.g., 'fi', 'en')")
        parser.add_argument(
            "--enable",
            nargs="+",
            help="Check IDs to enable (space-separated)",
        )
        parser.add_argument(
            "--disable",
            nargs="+",
            help="Check IDs to disable (space-separated)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset to run all checks (clear enabled_checks)",
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Show current configuration",
        )

    def handle(self, *args, **options):
        wiki_code = options["wiki_code"]

        try:
            wiki = Wiki.objects.get(code=wiki_code)
        except Wiki.DoesNotExist:
            raise CommandError(f"Wiki '{wiki_code}' not found")

        config, _ = WikiConfiguration.objects.get_or_create(wiki=wiki)

        if options["show"]:
            self._show_config(wiki, config)
            return

        if options["reset"]:
            config.enabled_checks = None
            config.save()
            self.stdout.write(
                self.style.SUCCESS(f"Reset checks for {wiki_code} - all checks will run")
            )
            return

        current_checks = set(config.enabled_checks or [])
        all_check_ids = {c["id"] for c in AVAILABLE_CHECKS}

        if options["enable"]:
            for check_id in options["enable"]:
                if check_id not in all_check_ids:
                    self.stdout.write(
                        self.style.WARNING(f"Unknown check ID: {check_id} (skipping)")
                    )
                    continue
                current_checks.add(check_id)
                self.stdout.write(self.style.SUCCESS(f"Enabled: {check_id}"))

        if options["disable"]:
            if not current_checks:
                current_checks = set(all_check_ids)

            for check_id in options["disable"]:
                if check_id in current_checks:
                    current_checks.remove(check_id)
                    self.stdout.write(self.style.SUCCESS(f"Disabled: {check_id}"))

        if options["enable"] or options["disable"]:
            config.enabled_checks = sorted(current_checks) if current_checks else None
            config.save()
            self.stdout.write(self.style.SUCCESS(f"\nUpdated configuration for {wiki_code}"))
            self._show_config(wiki, config)

    def _show_config(self, wiki, config):
        self.stdout.write(f"\nConfiguration for {wiki.name} ({wiki.code}):\n")

        if not config.enabled_checks:
            self.stdout.write(self.style.SUCCESS("  Status: All checks enabled (default)\n"))
            for check in sorted(AVAILABLE_CHECKS, key=lambda c: c["priority"]):
                self.stdout.write(f"  ✓ {check['id']}")
        else:
            enabled_ids = set(config.enabled_checks)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Status: {len(enabled_ids)}/{len(AVAILABLE_CHECKS)} checks enabled\n"
                )
            )

            for check in sorted(AVAILABLE_CHECKS, key=lambda c: c["priority"]):
                status = "✓" if check["id"] in enabled_ids else "✗"
                style = self.style.SUCCESS if check["id"] in enabled_ids else self.style.ERROR
                self.stdout.write(style(f"  {status} {check['id']}"))
