from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import requests

from reviews.models import PendingPage, PendingRevision, WordAnnotation

logger = logging.getLogger(__name__)


class WordAnnotationEngine:
    """Engine for annotating article revisions at word level."""

    def __init__(self, page: PendingPage):
        self.page = page
        self.wiki = page.wiki

    def annotate_revision(self, revision: PendingRevision) -> dict[str, Any]:
        """
        Annotate a single revision by comparing it with its parent.

        Returns dictionary with annotation results.
        """
        try:
            parent_revision = self._get_parent_revision(revision)
            if not parent_revision:
                # First revision - all words attributed to author
                return self._annotate_first_revision(revision)

            # Get diff from MediaWiki REST API
            diff_data = self._get_diff(parent_revision.revid, revision.revid)

            if not diff_data:
                return {"success": False, "error": "Could not fetch diff data"}

            # Annotate words based on diff
            annotations = self._process_diff(diff_data, revision, parent_revision)

            # Save annotations to database
            self._save_annotations(annotations, revision)

            return {
                "success": True,
                "revision_id": revision.revid,
                "words_annotated": len(annotations),
            }

        except Exception as e:
            logger.exception(f"Error annotating revision {revision.revid}: {e}")
            return {"success": False, "error": str(e)}

    def _get_parent_revision(
        self, revision: PendingRevision
    ) -> PendingRevision | None:
        """Get parent revision."""
        if not revision.parentid:
            return None

        return PendingRevision.objects.filter(
            page=revision.page, revid=revision.parentid
        ).first()

    def _get_diff(self, from_revid: int, to_revid: int) -> dict | None:
        """Fetch diff from MediaWiki REST API."""
        try:
            api_url = (
                f"https://{self.wiki.code}.wikipedia.org/"
                f"w/rest.php/v1/revision/{from_revid}/compare/{to_revid}"
            )

            headers = {
                "User-Agent": "PendingChangesBot/1.0 (https://github.com/Wikimedia-Suomi/PendingChangesBot-ng)"
            }
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.exception(f"Error fetching diff from REST API: {e}")
            return None

    def _annotate_first_revision(
        self, revision: PendingRevision
    ) -> dict[str, Any]:
        """Annotate first revision - all words attributed to author."""
        wikitext = revision.get_wikitext()
        if not wikitext:
            return {"success": False, "error": "No wikitext"}

        words = self._tokenize(wikitext)
        annotations = []

        for position, word in enumerate(words):
            word_id = self._generate_word_id(revision.revid, position, word)

            annotations.append(
                {
                    "word": word,
                    "stable_word_id": word_id,
                    "author_user_name": revision.user_name,
                    "author_user_id": revision.user_id,
                    "position": position,
                    "is_moved": False,
                    "is_modified": False,
                    "is_deleted": False,
                }
            )

        self._save_annotations(annotations, revision)
        return {
            "success": True,
            "revision_id": revision.revid,
            "words_annotated": len(annotations),
        }

    def _process_diff(
        self, diff_data: dict, revision: PendingRevision, parent_revision: PendingRevision
    ) -> list[dict[str, Any]]:
        """Process diff data to create annotations."""
        diff = diff_data.get("diff", [])
        annotations = []

        # Get existing annotations from parent
        parent_annotations = self._get_parent_annotations(parent_revision)

        position = 0
        for line in diff:
            line_type = line.get("type")
            text = line.get("text", "")

            if line_type == 0:  # Context (unchanged text)
                # Use annotations from parent
                words = self._tokenize(text)
                for word in words:
                    existing = self._find_parent_annotation(word, parent_annotations)
                    if existing:
                        annotations.append(
                            {
                                "word": word,
                                "stable_word_id": existing["stable_word_id"],
                                "author_user_name": existing["author_user_name"],
                                "author_user_id": existing["author_user_id"],
                                "position": position,
                                "is_moved": False,
                                "is_modified": False,
                                "is_deleted": False,
                            }
                        )
                    position += 1

            elif line_type == 1:  # Added text
                words = self._tokenize(text)
                for word in words:
                    # Check if this word was moved from elsewhere
                    moved_from = self._check_if_moved(word, parent_annotations)

                    if moved_from:
                        annotations.append(
                            {
                                "word": word,
                                "stable_word_id": moved_from["stable_word_id"],
                                "author_user_name": moved_from["author_user_name"],
                                "author_user_id": moved_from["author_user_id"],
                                "position": position,
                                "is_moved": True,
                                "is_modified": False,
                                "is_deleted": False,
                            }
                        )
                    else:
                        # New word
                        word_id = self._generate_word_id(revision.revid, position, word)
                        annotations.append(
                            {
                                "word": word,
                                "stable_word_id": word_id,
                                "author_user_name": revision.user_name,
                                "author_user_id": revision.user_id,
                                "position": position,
                                "is_moved": False,
                                "is_modified": False,
                                "is_deleted": False,
                            }
                        )
                    position += 1

            elif line_type == 2:  # Deleted text
                # Mark as deleted
                words = self._tokenize(text)
                for word in words:
                    word_id = self._generate_word_id(revision.revid, position, f"DELETED-{word}")
                    annotations.append(
                        {
                            "word": word,
                            "stable_word_id": word_id,
                            "author_user_name": revision.user_name,
                            "author_user_id": revision.user_id,
                            "position": position,
                            "is_moved": False,
                            "is_modified": False,
                            "is_deleted": True,
                        }
                    )
                    position += 1

        return annotations

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words with basic wikitext handling."""
        # Remove templates {{...}}
        text = re.sub(r'\{\{[^}]+\}\}', '', text)
        # Extract link text [[Article|text]] -> text or [[Article]] -> Article
        text = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', text)
        # Remove references
        text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<ref[^>]*/?>', '', text, flags=re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Remove category tags
        text = re.sub(r'\[\[Category:[^\]]+\]\]', '', text, flags=re.IGNORECASE)
        
        # Tokenize on whitespace
        words = re.split(r'(\s+)', text)
        # Filter out empty strings but keep whitespace for formatting
        return [w for w in words if w.strip() or w in ["\n", "\t", " "]]

    def _generate_word_id(self, revision_id: int, position: int, word: str) -> str:
        """Generate a stable word ID."""
        content = f"{revision_id}-{position}-{word}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _get_parent_annotations(
        self, parent_revision: PendingRevision
    ) -> list[dict[str, Any]]:
        """Get annotations from parent revision."""
        annotations = WordAnnotation.objects.filter(
            page=self.page, revision_id=parent_revision.revid
        ).order_by("position")

        return [
            {
                "stable_word_id": ann.stable_word_id,
                "author_user_name": ann.author_user_name,
                "author_user_id": ann.author_user_id,
                "word": ann.word,
            }
            for ann in annotations
        ]

    def _find_parent_annotation(self, word: str, parent_annotations: list[dict]) -> dict | None:
        """Find matching annotation from parent."""
        # Simple matching - can be enhanced
        for ann in parent_annotations:
            if ann["word"] == word:
                return ann
        return None

    def _check_if_moved(self, word: str, parent_annotations: list[dict]) -> dict | None:
        """Check if word was moved from another location."""
        # Look for exact word match in parent annotations
        # If the word exists in parent but in a different position, it might be moved
        for ann in parent_annotations:
            if ann["word"] == word:
                # Found matching word in parent - preserve original authorship
                return ann
        return None

    def _save_annotations(self, annotations: list[dict], revision: PendingRevision) -> None:
        """Save annotations to database."""
        WordAnnotation.objects.filter(page=self.page, revision_id=revision.revid).delete()

        for ann in annotations:
            WordAnnotation.objects.create(
                page=self.page,
                revision_id=revision.revid,
                stable_word_id=ann["stable_word_id"],
                word=ann["word"],
                author_user_name=ann["author_user_name"],
                author_user_id=ann["author_user_id"],
                position=ann["position"],
                is_moved=ann["is_moved"],
                is_modified=ann["is_modified"],
                is_deleted=ann["is_deleted"],
            )
