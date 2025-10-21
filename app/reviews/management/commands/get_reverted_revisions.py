from django.core.management.base import BaseCommand, CommandError
from reviews.models import PendingRevision, Wiki
import json
import pywikibot
from pywikibot.data.superset import SupersetQuery


class Command(BaseCommand):
    help = 'Find reverted revisions for a given wiki and check for older reviewed versions'

    def add_arguments(self, parser):
        parser.add_argument(
            'wiki_code',
            type=str,
            help='Wiki code (e.g., "fi", "en", "de")',
        )

    def handle(self, *args, **options):
        wiki_code = options['wiki_code']

        # Get the wiki
        try:
            wiki = Wiki.objects.get(code=wiki_code)
        except Wiki.DoesNotExist:
            raise CommandError(f'Wiki with code "{wiki_code}" does not exist')

        self.stdout.write(f'Using wiki: {wiki.name} ({wiki.code})')
        self.stdout.write('Searching for reverted revisions...')

        # Get all revisions from this wiki
        all_revisions = PendingRevision.objects.filter(
            page__wiki=wiki
        ).select_related('page')

        total_revisions = all_revisions.count()
        self.stdout.write(f'Total revisions in wiki: {total_revisions}')

        reverted_revids = set()

        # Extract reverted revision IDs from change_tag_params
        for revision in all_revisions:
            params_str = getattr(revision, 'change_tag_params', None)
            if not params_str:
                continue

            try:
                json_parts = params_str.split('},')
                for part in json_parts:
                    if not part.endswith('}'):
                        part += '}'

                    data = json.loads(part)
                    if 'originalRevisionId' in data:
                        reverted_revids.add(data['originalRevisionId'])
                    if 'revertId' in data:
                        reverted_revids.add(data['revertId'])
            except json.JSONDecodeError:
                continue

        reverted_revids = list(reverted_revids)
        self.stdout.write(self.style.SUCCESS(f'Found {len(reverted_revids)} reverted revisions'))

        if not reverted_revids:
            self.stdout.write(self.style.WARNING('No reverted revisions found, skipping query'))
            return

        # Review check query
        self.stdout.write('\nExecuting review check query...')

        site = pywikibot.Site(wiki_code, "wikipedia")
        superset = SupersetQuery(site=site)

        revert_id_list = ','.join(map(str, reverted_revids))
        sql = f"""
            SELECT
                MAX(rev_id) as max_reviewable_rev_id_by_sha1,
                rev_page,
                content_sha1,
                MAX(fr_rev_id) as max_old_reviewed_id
            FROM
                revision
                LEFT JOIN flaggedrevs ON rev_id=fr_rev_id
                JOIN slots ON slot_revision_id=rev_id
                JOIN content ON slot_content_id=content_id
            WHERE
                rev_id IN ({revert_id_list})
            GROUP BY
                rev_page, content_sha1;
        """

        try:
            results = superset.query(sql)
            self.stdout.write(self.style.SUCCESS(
                f'Review check query returned {len(results)} results')
            )

            for row in results:
                if row['max_old_reviewed_id'] is not None and row['max_reviewable_rev_id_by_sha1']:
                    self.stdout.write(
                        f"Page {row['rev_page']} has reviewed (old ID: {row['max_old_reviewed_id']})")

            for reverted_rev_id in reverted_revids:
                for row in results:
                    max_reviewable_rev_id_by_sha1 = row['max_reviewable_rev_id_by_sha1']
                    max_old_reviewed_id = row['max_old_reviewed_id']

                    if reverted_rev_id <= max_reviewable_rev_id_by_sha1 and max_old_reviewed_id is not None:
                        self.stdout.write(f"Auto-approving revision {reverted_rev_id}...")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error executing Superset query: {str(e)}'))
            raise
