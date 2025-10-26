from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from reviews.annotations import WordAnnotationEngine
from reviews.models import PendingPage, PendingRevision


class Command(BaseCommand):
    help = "Annotate article history with word-level authorship tracking"

    def add_arguments(self, parser):
        parser.add_argument("page_id", type=int, help="Page ID to annotate")
        parser.add_argument(
            "--start-revision",
            type=int,
            help="Start revision ID (default: first revision)",
        )
        parser.add_argument(
            "--end-revision",
            type=int,
            help="End revision ID (default: latest revision)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        page_id = options["page_id"]
        start_revid = options.get("start_revision")
        end_revid = options.get("end_revision")

        try:
            page = PendingPage.objects.get(pageid=page_id)
        except PendingPage.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Page with ID {page_id} not found"))
            return

        self.stdout.write(self.style.SUCCESS(f"\n=== Annotating Article: {page.title} ===\n"))

        # Get revisions to annotate
        revisions = PendingRevision.objects.filter(page=page).order_by("revid")

        if start_revid:
            revisions = revisions.filter(revid__gte=start_revid)
        if end_revid:
            revisions = revisions.filter(revid__lte=end_revid)

        total = revisions.count()
        self.stdout.write(f"Found {total} revisions to annotate\n")

        # Create annotation engine
        engine = WordAnnotationEngine(page)

        # Annotate each revision
        processed = 0
        for revision in revisions:
            self.stdout.write(f"Processing revision {revision.revid}...", ending=" ")

            result = engine.annotate_revision(revision)

            if result["success"]:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"OK ({result['words_annotated']} words annotated)"
                    )
                )
                processed += 1
            else:
                self.stdout.write(
                    self.style.ERROR(f"FAILED: {result.get('error', 'Unknown error')}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n\nCompleted: {processed}/{total} revisions annotated successfully"
            )
        )
