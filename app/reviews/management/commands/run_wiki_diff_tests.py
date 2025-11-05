from __future__ import annotations

import contextlib
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pywikibot
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from reviews.autoreview.checks import get_check_by_id
from reviews.autoreview.context import CheckContext
from reviews.autoreview.utils.redirect import get_redirect_aliases
from reviews.autoreview.utils.user import normalize_to_lookup
from reviews.models import (
    EditorProfile,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)
from reviews.services import WikiClient

LINE_PATTERN = re.compile(
    r"^\*\s+(?P<url>\S+)\s+(?P<test_id>[^:]+?)\s*:\s*(?P<expected>[^#]*?)"
    r"(?:\s+#\s*(?P<comment>.*))?$"
)

AUTOREVIEWED_GROUPS = {"autoreview", "autoreviewer", "editor", "reviewer", "sysop", "bot"}


@dataclass
class WikiDiffTest:
    url: str
    test_id: str
    expected: str
    revid: int
    oldid: int | None
    comment: str | None = None


class Command(BaseCommand):
    help = (
        "Load wiki diff tests from Käyttäjä:SeulojaBot/testedits, "
        "execute the configured checks for each revision and compare the results."
    )

    default_wiki_code = "fi"
    default_page_title = "Käyttäjä:SeulojaBot/testedits"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--page",
            default=self.default_page_title,
            help="Title of the wiki page that lists the diff tests.",
        )
        parser.add_argument(
            "--wiki",
            default=self.default_wiki_code,
            help="Wiki code (language) for the page. Defaults to 'fi'.",
        )
        parser.add_argument(
            "--family",
            default="wikipedia",
            help="Pywikibot family for the wiki. Defaults to 'wikipedia'.",
        )

    def handle(self, *args, **options):
        page_title: str = options["page"]
        wiki_code: str = options["wiki"]
        wiki_family: str = options["family"]

        wiki = self._ensure_wiki(wiki_code, wiki_family)
        site = pywikibot.Site(code=wiki.code, fam=wiki.family)

        wikitext = self._fetch_wikitext(site, page_title)
        tests = list(self._parse_tests(wikitext))
        if not tests:
            self.stdout.write(self.style.WARNING("No tests found on the page."))
            return

        WikiConfiguration.objects.get_or_create(wiki=wiki)
        redirect_aliases = get_redirect_aliases(wiki)
        client = WikiClient(wiki)
        configuration = wiki.configuration
        auto_groups = normalize_to_lookup(configuration.auto_approved_groups)
        blocking_categories = normalize_to_lookup(configuration.blocking_categories)

        passes = 0
        failures = 0
        first_check = True

        for entry in tests:
            if not first_check:
                self.stdout.write("")
                self.stdout.write("=" * 80)
                self.stdout.write("")
            else:
                first_check = False

            check_info = get_check_by_id(entry.test_id.strip())
            if not check_info:
                failures += 1
                self.stdout.write(
                    self.style.ERROR(f"Unknown test id '{entry.test_id}' for URL {entry.url}.")
                )
                continue

            revision = self._ensure_revision(site, wiki, entry.revid, entry.oldid)
            if not revision:
                failures += 1
                self.stdout.write(
                    self.style.ERROR(f"Could not load revision {entry.revid} for URL {entry.url}.")
                )
                continue

            profile = self._ensure_editor_profile(site, wiki, revision)
            context = CheckContext(
                revision=revision,
                client=client,
                profile=profile,
                auto_groups=auto_groups,
                blocking_categories=blocking_categories,
                redirect_aliases=redirect_aliases,
            )

            try:
                result = check_info["function"](context)
            except Exception as exc:  # pragma: no cover - defensive programming
                failures += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Check '{entry.test_id}' failed for revision {entry.revid}: {exc}"
                    )
                )
                continue

            expected = self._normalize_expected(entry.expected)
            actual = self._normalize_expected(result.status)
            decision_status = (
                self._normalize_expected(result.decision.status) if result.decision else None
            )

            matches = expected in {actual, decision_status}

            status_text = f"expected={entry.expected.strip()} actual={result.status}"
            if result.decision:
                status_text += f" decision={result.decision.status}"

            if matches:
                passes += 1
                self.stdout.write(
                    self.style.SUCCESS(f"PASS {entry.revid} {entry.test_id}: {status_text}")
                )
            else:
                failures += 1
                self.stdout.write(
                    self.style.ERROR(f"FAIL {entry.revid} {entry.test_id}: {status_text}")
                )
                self.stdout.write(f"    Status: {result.status}")
                self.stdout.write(f"    Message: {result.message}")
                self.stdout.write(f"    Diff URL: {entry.url}")
                diff_text = self._get_failure_diff(site, wiki, revision, entry)
                if diff_text:
                    self.stdout.write("    Diff:")
                    for line in diff_text.rstrip().splitlines():
                        self.stdout.write(f"        {line}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Passes: {passes}") if passes else "Passes: 0")
        self.stdout.write(self.style.ERROR(f"Failures: {failures}") if failures else "Failures: 0")

    def _ensure_wiki(self, code: str, family: str) -> Wiki:
        api_endpoint = f"https://{code}.wikipedia.org/w/api.php"
        defaults = {
            "name": f"{code}.wikipedia",
            "family": family,
            "api_endpoint": api_endpoint,
            "script_path": "/w",
        }
        wiki, _ = Wiki.objects.get_or_create(code=code, defaults=defaults)
        return wiki

    def _fetch_wikitext(self, site: pywikibot.Site, title: str) -> str:
        page = pywikibot.Page(site, title)
        try:
            return page.get()
        except Exception:  # pragma: no cover - network failures handled at runtime
            self.stderr.write(self.style.ERROR(f"Failed to fetch page '{title}'."))
            return ""

    def _parse_tests(self, wikitext: str) -> Iterable[WikiDiffTest]:
        for line in wikitext.splitlines():
            match = LINE_PATTERN.match(line.strip())
            if not match:
                continue

            url = match.group("url")
            test_id = match.group("test_id").strip()
            expected = match.group("expected").strip()
            comment = (match.group("comment") or "").strip() or None

            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            diff = self._parse_int(params.get("diff", [None])[0])
            oldid = self._parse_int(params.get("oldid", [None])[0])

            if not diff:
                continue

            yield WikiDiffTest(
                url=url,
                test_id=test_id,
                expected=expected,
                revid=diff,
                oldid=oldid,
                comment=comment,
            )

    def _parse_int(self, value: int | str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _ensure_revision(
        self,
        site: pywikibot.Site,
        wiki: Wiki,
        revid: int,
        oldid: int | None,
        *,
        update_page_defaults: bool = True,
    ) -> PendingRevision | None:
        revision = (
            PendingRevision.objects.select_related("page")
            .filter(page__wiki=wiki, revid=revid)
            .first()
        )
        if revision and revision.wikitext:
            return revision

        try:
            request = site.simple_request(
                action="query",
                prop="revisions|info|categories",
                revids=str(revid),
                rvslots="main",
                rvprop="ids|timestamp|user|userid|comment|sha1|content|tags",
                cllimit="max",
                clshow="!hidden",
                formatversion=2,
            )
            response = request.submit()
        except Exception as exc:  # pragma: no cover - network failures handled at runtime
            self.stderr.write(self.style.ERROR(f"Failed to fetch revision {revid} from API: {exc}"))
            return revision

        pages = response.get("query", {}).get("pages", [])
        if not pages:
            return revision

        page_data = pages[0]
        revisions = page_data.get("revisions") or []
        if not revisions:
            return revision

        revision_data = revisions[0]
        timestamp = self._parse_timestamp(revision_data.get("timestamp"))
        if timestamp is None:
            timestamp = timezone.now()

        with transaction.atomic():
            page_defaults = {
                "title": page_data.get("title", ""),
            }
            if update_page_defaults:
                page_defaults["pending_since"] = None
            if update_page_defaults:
                page_defaults["stable_revid"] = oldid or revision_data.get("parentid") or 0

            categories = [
                category.get("title")
                for category in page_data.get("categories", [])
                if isinstance(category, dict) and category.get("title")
            ]
            if categories:
                page_defaults["categories"] = categories

            page, _ = PendingPage.objects.update_or_create(
                wiki=wiki,
                pageid=self._parse_int(page_data.get("pageid")) or 0,
                defaults=page_defaults,
            )

            slots = revision_data.get("slots", {})
            main_slot = slots.get("main", {}) if isinstance(slots, dict) else {}
            wikitext = main_slot.get("content") or ""

            change_tags = revision_data.get("tags") or []
            if not isinstance(change_tags, list):
                change_tags = []

            age = timezone.now() - timestamp
            if age < timedelta(0):
                age = timedelta(0)

            defaults = {
                "parentid": revision_data.get("parentid"),
                "user_name": revision_data.get("user") or "",
                "user_id": revision_data.get("userid"),
                "timestamp": timestamp,
                "age_at_fetch": age,
                "sha1": revision_data.get("sha1") or "",
                "comment": revision_data.get("comment") or "",
                "change_tags": change_tags,
                "wikitext": wikitext,
            }

            revision, _ = PendingRevision.objects.update_or_create(
                page=page,
                revid=self._parse_int(revision_data.get("revid")) or revid,
                defaults=defaults,
            )

        if revision and update_page_defaults:
            self._ensure_related_revisions(
                site,
                wiki,
                revision,
                parent_candidates={oldid, revision.parentid},
            )

        return revision

    def _ensure_related_revisions(
        self,
        site: pywikibot.Site,
        wiki: Wiki,
        revision: PendingRevision,
        parent_candidates: set[int | None],
    ) -> None:
        parent_ids: set[int] = set()
        for parent in parent_candidates:
            parsed = self._parse_int(parent)
            if parsed:
                parent_ids.add(parsed)
        if not parent_ids:
            return

        for parent_id in parent_ids:
            if not parent_id:
                continue

            parent_revision = PendingRevision.objects.filter(
                page=revision.page, revid=parent_id
            ).first()
            if parent_revision and parent_revision.wikitext:
                continue

            self._ensure_revision(
                site,
                wiki,
                parent_id,
                None,
                update_page_defaults=False,
            )

    def _parse_timestamp(self, value: str | None):
        if not value:
            return None
        timestamp = parse_datetime(value)
        if timestamp is None:
            return None
        if timezone.is_naive(timestamp):
            timestamp = timezone.make_aware(timestamp, timezone=timezone.utc)
        return timestamp

    def _ensure_editor_profile(
        self, site: pywikibot.Site, wiki: Wiki, revision: PendingRevision
    ) -> EditorProfile | None:
        username = revision.user_name
        if not username:
            return None

        profile = EditorProfile.objects.filter(wiki=wiki, username=username).first()
        if profile and not profile.is_expired:
            return profile

        try:
            request = site.simple_request(
                action="query",
                list="users",
                ususers=username,
                usprop="groups|blockinfo",
                formatversion=2,
            )
            response = request.submit()
        except Exception as exc:  # pragma: no cover - network failures handled at runtime
            self.stderr.write(self.style.ERROR(f"Failed to fetch user data for {username}: {exc}"))
            return profile

        users = response.get("query", {}).get("users", [])
        if not users:
            return profile

        user_data = users[0]
        groups = [str(group) for group in user_data.get("groups", []) if group]
        is_blocked = "blockedby" in user_data
        is_bot = "bot" in groups
        is_autopatrolled = "autopatrolled" in groups
        is_autoreviewed = bool(AUTOREVIEWED_GROUPS & set(groups))

        defaults = {
            "usergroups": groups,
            "is_blocked": is_blocked,
            "is_bot": is_bot,
            "is_former_bot": False,
            "is_autopatrolled": is_autopatrolled,
            "is_autoreviewed": is_autoreviewed,
        }

        profile, _ = EditorProfile.objects.update_or_create(
            wiki=wiki,
            username=username,
            defaults=defaults,
        )

        superset_data = revision.superset_data or {}
        changed = False
        if superset_data.get("user_groups") != groups:
            superset_data["user_groups"] = groups
            changed = True
        if superset_data.get("user_blocked") != is_blocked:
            superset_data["user_blocked"] = is_blocked
            changed = True
        if superset_data.get("rc_bot") != is_bot:
            superset_data["rc_bot"] = is_bot
            changed = True

        if changed:
            revision.superset_data = superset_data
            revision.save(update_fields=["superset_data"])

        return profile

    def _normalize_expected(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = value.strip().lower().replace(" ", "_")
        return normalized.replace("-", "_")

    def _get_failure_diff(
        self,
        site: pywikibot.Site,
        wiki: Wiki,
        revision: PendingRevision,
        entry: WikiDiffTest,
    ) -> str:
        if not revision.wikitext:
            return ""

        base_revision = self._resolve_base_revision(site, wiki, revision, entry)
        if not base_revision or not base_revision.wikitext:
            return ""

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            pywikibot.showDiff(base_revision.wikitext, revision.wikitext)
        return buffer.getvalue()

    def _resolve_base_revision(
        self,
        site: pywikibot.Site,
        wiki: Wiki,
        revision: PendingRevision,
        entry: WikiDiffTest,
    ) -> PendingRevision | None:
        candidates: list[int | None] = [entry.oldid, revision.parentid]
        for candidate in candidates:
            candidate_id = self._parse_int(candidate)
            if not candidate_id:
                continue

            existing = PendingRevision.objects.filter(
                page=revision.page, revid=candidate_id
            ).first()
            if existing and existing.wikitext:
                return existing

            fetched = self._ensure_revision(
                site,
                wiki,
                candidate_id,
                None,
                update_page_defaults=False,
            )
            if fetched and fetched.wikitext:
                return fetched

        return None
