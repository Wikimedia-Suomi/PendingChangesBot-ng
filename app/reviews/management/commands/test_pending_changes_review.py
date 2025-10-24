"""
Django management command to test pending changes review functionality.

This command allows testing the approve_revision() utility function
with various parameters and configurations.
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from reviews.utils.approval import approve_revision


class Command(BaseCommand):
    help = 'Test pending changes review functionality (approve/unapprove revisions)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--revid',
            type=int,
            required=True,
            help='Revision ID to approve/unapprove'
        )
        parser.add_argument(
            '--comment',
            type=str,
            default='Test approval via management command',
            help='Comment for the review (default: "Test approval via management command")'
        )
        parser.add_argument(
            '--unapprove',
            action='store_true',
            help='Unapprove the revision instead of approving it'
        )
        parser.add_argument(
            '--value',
            type=int,
            help='Flag value for the review (optional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making actual changes'
        )

    def handle(self, *args, **options):
        revid = options['revid']
        comment = options['comment']
        unapprove = options['unapprove']
        value = options['value']
        dry_run = options['dry_run']

        # Display current configuration
        self.stdout.write(f"Current PENDING_CHANGES_DRY_RUN setting: {getattr(settings, 'PENDING_CHANGES_DRY_RUN', True)}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN MODE: No actual changes will be made"))
        
        # Display operation details
        operation = "unapprove" if unapprove else "approve"
        self.stdout.write(f"Operation: {operation}")
        self.stdout.write(f"Revision ID: {revid}")
        self.stdout.write(f"Comment: {comment}")
        if value is not None:
            self.stdout.write(f"Value: {value}")
        
        try:
            # Call the approve_revision function
            result = approve_revision(
                revid=revid,
                comment=comment,
                value=value,
                unapprove=unapprove
            )
            
            # Display results
            if result['result'] == 'success':
                if result.get('dry_run', False):
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ {result['message']}")
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ {result['message']}")
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(f"❌ {result['message']}")
                )
            
            # Display additional information
            if 'api_response' in result:
                self.stdout.write(f"API Response: {result['api_response']}")
            
            # Display dry-run information
            if result.get('dry_run', False):
                self.stdout.write(
                    self.style.WARNING(
                        "ℹ️  This was a dry-run operation. "
                        "Set PENDING_CHANGES_DRY_RUN=False to make actual changes."
                    )
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error: {str(e)}")
            )
            raise CommandError(f"Failed to {operation} revision {revid}: {str(e)}")
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Command completed successfully")
        )
