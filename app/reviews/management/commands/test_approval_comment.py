"""
Django management command for testing approval comment generation.
This command provides a comprehensive testing interface for the approval comment
generation functionality with multiple scenarios and preview capabilities.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from reviews.utils.approval_comment import generate_approval_comment
from reviews.utils.approval_processor import (
    get_approval_statistics,
    preview_approval_comment,
    process_and_approve_revisions,
)


class Command(BaseCommand):
    help = "Test approval comment generation with various scenarios"

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario",
            type=str,
            choices=["bot", "ores", "mixed", "none", "single", "all"],
            default="all",
            help="Test scenario to run (default: all)",
        )
        parser.add_argument(
            "--comment-prefix", type=str, default="", help="Prefix to add to approval comments"
        )
        parser.add_argument(
            "--preview-only", action="store_true", help="Only preview comments without processing"
        )
        parser.add_argument("--verbose", action="store_true", help="Show detailed output")

    def handle(self, *args, **options):
        scenario = options["scenario"]
        comment_prefix = options["comment_prefix"]
        preview_only = options["preview_only"]
        verbose = options["verbose"]

        self.stdout.write(
            self.style.SUCCESS(f"Testing approval comment generation - Scenario: {scenario}")
        )

        if scenario == "all":
            scenarios = ["bot", "ores", "mixed", "none", "single"]
        else:
            scenarios = [scenario]

        for test_scenario in scenarios:
            self.stdout.write(f"\n--- Testing Scenario: {test_scenario.upper()} ---")
            self._run_scenario(test_scenario, comment_prefix, preview_only, verbose)

        self.stdout.write(self.style.SUCCESS("\nAll tests completed successfully!"))

    def _run_scenario(self, scenario: str, comment_prefix: str, preview_only: bool, verbose: bool):
        """Run a specific test scenario."""
        test_data = self._get_test_data(scenario)

        if verbose:
            self.stdout.write(f"Test data: {test_data}")

        # Test basic comment generation
        max_revid, comment = generate_approval_comment(test_data, comment_prefix)
        self.stdout.write(f"Max approvable revision ID: {max_revid}")
        self.stdout.write(f"Generated comment: {comment}")

        # Test with processor
        if preview_only:
            result = preview_approval_comment(test_data, comment_prefix)
            self.stdout.write(f'Preview mode: {result.get("message", "preview generated")}')
        else:
            result = process_and_approve_revisions(test_data, comment_prefix, dry_run=True)
            self.stdout.write(f'Processing result: {result["message"]}')

        # Show statistics
        stats = get_approval_statistics(test_data)
        self.stdout.write(
            f'Statistics: {stats["approved_count"]}/{stats["total_revisions"]} approved ({stats["approval_rate"]:.1f}%)'
        )

        if verbose:
            self.stdout.write(f"Full statistics: {stats}")

    def _get_test_data(self, scenario: str) -> list:
        """Generate test data for different scenarios."""
        now = timezone.now()

        if scenario == "bot":
            return [
                {
                    "revid": 12345,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "user was bot",
                    },
                },
                {
                    "revid": 12346,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "user was bot",
                    },
                },
            ]

        elif scenario == "ores":
            return [
                {
                    "revid": 12347,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "ORES score goodfaith=0.53, damaging: 0.251",
                    },
                }
            ]

        elif scenario == "mixed":
            return [
                {
                    "revid": 12345,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "user was bot",
                    },
                },
                {
                    "revid": 12346,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "no content change in last article",
                    },
                },
                {
                    "revid": 12347,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "user was autoreviewed",
                    },
                },
                {
                    "revid": 12348,
                    "tests": [],
                    "decision": {
                        "status": "blocked",
                        "label": "Cannot be auto-approved",
                        "reason": "user was blocked",
                    },
                },
                {
                    "revid": 12349,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "ORES score goodfaith=0.53, damaging: 0.251",
                    },
                },
            ]

        elif scenario == "none":
            return [
                {
                    "revid": 12350,
                    "tests": [],
                    "decision": {
                        "status": "blocked",
                        "label": "Cannot be auto-approved",
                        "reason": "user was blocked",
                    },
                },
                {
                    "revid": 12351,
                    "tests": [],
                    "decision": {
                        "status": "manual",
                        "label": "Requires human review",
                        "reason": "requires human review",
                    },
                },
            ]

        elif scenario == "single":
            return [
                {
                    "revid": 12352,
                    "tests": [],
                    "decision": {
                        "status": "approve",
                        "label": "Would be auto-approved",
                        "reason": "user was bot",
                    },
                }
            ]

        else:
            return []

    def _show_usage_examples(self):
        """Show usage examples."""
        self.stdout.write("\nUsage Examples:")
        self.stdout.write(
            "  python manage.py test_approval_comment --scenario mixed --preview-only"
        )
        self.stdout.write(
            '  python manage.py test_approval_comment --scenario bot --comment-prefix "Auto: "'
        )
        self.stdout.write("  python manage.py test_approval_comment --scenario all --verbose")
