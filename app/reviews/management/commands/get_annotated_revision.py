from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from reviews.models import PendingPage, PendingRevision, WordAnnotation


class Command(BaseCommand):
    help = "Get annotated revision data"

    def add_arguments(self, parser):
        parser.add_argument("page_id", type=int, help="Page ID")
        parser.add_argument("revision_id", type=int, help="Revision ID to retrieve")
        parser.add_argument(
            "--author",
            type=str,
            help="Filter by author username",
        )
        parser.add_argument(
            "--only-new",
            action="store_true",
            help="Show only words added in this revision",
        )
        parser.add_argument(
            "--output",
            type=str,
            choices=["json", "text", "summary"],
            default="summary",
            help="Output format",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        page_id = options["page_id"]
        revision_id = options["revision_id"]
        author_filter = options.get("author")
        only_new = options.get("only_new", False)
        output_format = options["output"]

        try:
            page = PendingPage.objects.get(pageid=page_id)
        except PendingPage.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Page with ID {page_id} not found"))
            return

        # Get revision
        try:
            revision = PendingRevision.objects.get(page=page, revid=revision_id)
        except PendingRevision.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"Revision {revision_id} not found for page {page_id}")
            )
            return

        # Get annotations
        annotations = WordAnnotation.objects.filter(page=page, revision_id=revision_id).order_by(
            "position"
        )

        if author_filter:
            annotations = annotations.filter(author_user_name=author_filter)

        if only_new:
            # Only show words that are not marked as deleted and don't exist in parent
            # This is a simplified check
            annotations = annotations.exclude(is_deleted=True)

        if output_format == "json":
            self._output_json(annotations, revision)
        elif output_format == "text":
            self._output_text(annotations)
        else:
            self._output_summary(annotations, revision)

    def _output_json(self, annotations, revision):
        """Output as JSON."""
        data = {
            "revision_id": revision.revid,
            "page_title": revision.page.title,
            "timestamp": revision.timestamp.isoformat(),
            "user": revision.user_name,
            "comment": revision.comment,
            "words": [
                {
                    "word": ann.word,
                    "stable_word_id": ann.stable_word_id,
                    "author": ann.author_user_name,
                    "position": ann.position,
                    "is_moved": ann.is_moved,
                    "is_modified": ann.is_modified,
                    "is_deleted": ann.is_deleted,
                }
                for ann in annotations
            ],
        }
        self.stdout.write(json.dumps(data, indent=2))

    def _output_text(self, annotations):
        """Output as plain text."""
        for ann in annotations:
            status = ""
            if ann.is_deleted:
                status = "[DELETED]"
            elif ann.is_moved:
                status = "[MOVED]"
            elif ann.is_modified:
                status = "[MODIFIED]"

            self.stdout.write(f"[{ann.author_user_name}] {status} {ann.word}")

    def _output_summary(self, annotations, revision):
        """Output summary."""
        self.stdout.write(self.style.SUCCESS(f"\n=== Revision {revision.revid} ==="))
        self.stdout.write(f"Page: {revision.page.title}")
        self.stdout.write(f"Timestamp: {revision.timestamp}")
        self.stdout.write(f"User: {revision.user_name}")
        self.stdout.write(f"Comment: {revision.comment}")
        self.stdout.write(f"\nTotal words: {annotations.count()}")

        # Count by author
        authors = {}
        for ann in annotations:
            author = ann.author_user_name or "Anonymous"
            authors[author] = authors.get(author, 0) + 1

        self.stdout.write("\nWords by author:")
        for author, count in sorted(authors.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {author}: {count}")

        # Show some example words
        self.stdout.write("\nWord samples:")
        for ann in annotations[:20]:
            self.stdout.write(f"  [{ann.author_user_name}] {ann.word}")

        if annotations.count() > 20:
            self.stdout.write(f"  ... and {annotations.count() - 20} more words")
