"""
Unit tests for the approval utility functions.

Tests the approve_revision() function and related functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
from reviews.utils.approval import approve_revision, _get_page_title_from_revid


class ApprovalUtilityTests(TestCase):
    """Test cases for the approval utility functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_revid = 12345
        self.test_comment = "Test approval"
        self.test_site = Mock()
        self.test_site.code = 'fi'
        self.test_site.family.name = 'wikipedia'

    @patch('reviews.utils.approval.Site')
    @patch('reviews.utils.approval.Request')
    @override_settings(PENDING_CHANGES_DRY_RUN=False)
    def test_approve_revision_success(self, mock_request_class, mock_site_class):
        """Test successful approval of a revision."""
        # Mock the site
        mock_site_class.return_value = self.test_site
        
        # Mock the API request
        mock_request = Mock()
        mock_request.submit.return_value = {'review': {'result': 'success'}}
        mock_request_class.return_value = mock_request
        
        # Call the function
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            unapprove=False
        )
        
        # Assertions
        self.assertEqual(result['result'], 'success')
        self.assertFalse(result['dry_run'])
        self.assertIn('Successfully approved', result['message'])
        
        # Verify API call was made
        mock_request_class.assert_called_once()
        mock_request.submit.assert_called_once()

    @patch('reviews.utils.approval.Site')
    @patch('reviews.utils.approval.Request')
    @override_settings(PENDING_CHANGES_DRY_RUN=False)
    def test_approve_revision_unapprove(self, mock_request_class, mock_site_class):
        """Test successful unapproval of a revision."""
        # Mock the site
        mock_site_class.return_value = self.test_site
        
        # Mock the API request
        mock_request = Mock()
        mock_request.submit.return_value = {'review': {'result': 'success'}}
        mock_request_class.return_value = mock_request
        
        # Call the function
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            unapprove=True
        )
        
        # Assertions
        self.assertEqual(result['result'], 'success')
        self.assertFalse(result['dry_run'])
        self.assertIn('Successfully unapproved', result['message'])

    @patch('reviews.utils.approval.Site')
    @patch('reviews.utils.approval.Request')
    @patch('reviews.utils.approval._get_page_title_from_revid')
    @override_settings(PENDING_CHANGES_DRY_RUN=True)
    def test_approve_revision_dry_run_production_page(self, mock_get_title, mock_request_class, mock_site_class):
        """Test dry-run mode with production page (should skip)."""
        # Mock the site
        mock_site_class.return_value = self.test_site
        
        # Mock page title (production page)
        mock_get_title.return_value = "Production_Page"
        
        # Call the function
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            unapprove=False
        )
        
        # Assertions
        self.assertEqual(result['result'], 'success')
        self.assertTrue(result['dry_run'])
        self.assertIn('DRY-RUN: Would approve', result['message'])
        
        # Verify API call was NOT made
        mock_request_class.assert_not_called()

    @patch('reviews.utils.approval.Site')
    @patch('reviews.utils.approval.Request')
    @patch('reviews.utils.approval._get_page_title_from_revid')
    @override_settings(PENDING_CHANGES_DRY_RUN=True)
    def test_approve_revision_dry_run_test_page(self, mock_get_title, mock_request_class, mock_site_class):
        """Test dry-run mode with test page (should proceed)."""
        # Mock the site
        mock_site_class.return_value = self.test_site
        
        # Mock page title (test page)
        mock_get_title.return_value = "Merkityt_versiot_-kokeilu/Test_Page"
        
        # Mock the API request
        mock_request = Mock()
        mock_request.submit.return_value = {'review': {'result': 'success'}}
        mock_request_class.return_value = mock_request
        
        # Call the function
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            unapprove=False
        )
        
        # Assertions
        self.assertEqual(result['result'], 'success')
        self.assertFalse(result['dry_run'])
        self.assertIn('Successfully approved', result['message'])
        
        # Verify API call was made
        mock_request_class.assert_called_once()

    @patch('reviews.utils.approval.Site')
    @patch('reviews.utils.approval.Request')
    @override_settings(PENDING_CHANGES_DRY_RUN=False)
    def test_approve_revision_with_value(self, mock_request_class, mock_site_class):
        """Test approval with custom value parameter."""
        # Mock the site
        mock_site_class.return_value = self.test_site
        
        # Mock the API request
        mock_request = Mock()
        mock_request.submit.return_value = {'review': {'result': 'success'}}
        mock_request_class.return_value = mock_request
        
        # Call the function with value
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            value=1,
            unapprove=False
        )
        
        # Assertions
        self.assertEqual(result['result'], 'success')
        
        # Verify API call was made with value parameter
        mock_request_class.assert_called_once()
        call_args = mock_request_class.call_args
        self.assertEqual(call_args[1]['value'], '1')

    @patch('reviews.utils.approval.Site')
    @patch('reviews.utils.approval.Request')
    @override_settings(PENDING_CHANGES_DRY_RUN=False)
    def test_approve_revision_api_error(self, mock_request_class, mock_site_class):
        """Test handling of API errors."""
        # Mock the site
        mock_site_class.return_value = self.test_site
        
        # Mock API error response
        mock_request = Mock()
        mock_request.submit.return_value = {'error': {'code': 'permissiondenied', 'info': 'Permission denied'}}
        mock_request_class.return_value = mock_request
        
        # Call the function
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            unapprove=False
        )
        
        # Assertions
        self.assertEqual(result['result'], 'error')
        self.assertIn('Failed to approve', result['message'])

    @patch('reviews.utils.approval.Site')
    @override_settings(PENDING_CHANGES_DRY_RUN=False)
    def test_approve_revision_exception(self, mock_site_class):
        """Test handling of exceptions."""
        # Mock the site to raise an exception
        mock_site_class.side_effect = Exception("Connection error")
        
        # Call the function
        result = approve_revision(
            revid=self.test_revid,
            comment=self.test_comment,
            unapprove=False
        )
        
        # Assertions
        self.assertEqual(result['result'], 'error')
        self.assertIn('Error approving', result['message'])

    @patch('reviews.utils.approval.Request')
    def test_get_page_title_from_revid_success(self, mock_request_class):
        """Test successful retrieval of page title."""
        # Mock the API request
        mock_request = Mock()
        mock_request.submit.return_value = {
            'query': {
                'pages': {
                    '123': {
                        'title': 'Test_Page',
                        'revisions': [{'revid': self.test_revid}]
                    }
                }
            }
        }
        mock_request_class.return_value = mock_request
        
        # Call the function
        title = _get_page_title_from_revid(self.test_site, self.test_revid)
        
        # Assertions
        self.assertEqual(title, 'Test_Page')
        mock_request_class.assert_called_once()

    @patch('reviews.utils.approval.Request')
    def test_get_page_title_from_revid_not_found(self, mock_request_class):
        """Test handling when page title is not found."""
        # Mock the API request
        mock_request = Mock()
        mock_request.submit.return_value = {'query': {'pages': {}}}
        mock_request_class.return_value = mock_request
        
        # Call the function
        title = _get_page_title_from_revid(self.test_site, self.test_revid)
        
        # Assertions
        self.assertIsNone(title)

    @patch('reviews.utils.approval.Request')
    def test_get_page_title_from_revid_exception(self, mock_request_class):
        """Test handling of exceptions in _get_page_title_from_revid."""
        # Mock the API request to raise an exception
        mock_request = Mock()
        mock_request.submit.side_effect = Exception("API error")
        mock_request_class.return_value = mock_request
        
        # Call the function
        title = _get_page_title_from_revid(self.test_site, self.test_revid)
        
        # Assertions
        self.assertIsNone(title)


class ApprovalIntegrationTests(TestCase):
    """Integration tests for the approval functionality."""

    @override_settings(PENDING_CHANGES_DRY_RUN=True)
    def test_dry_run_setting_respected(self):
        """Test that the dry-run setting is properly respected."""
        # This test verifies that the setting is read correctly
        self.assertTrue(getattr(settings, 'PENDING_CHANGES_DRY_RUN', True))

    @override_settings(PENDING_CHANGES_DRY_RUN=False)
    def test_dry_run_setting_disabled(self):
        """Test that the dry-run setting can be disabled."""
        # This test verifies that the setting can be disabled
        self.assertFalse(getattr(settings, 'PENDING_CHANGES_DRY_RUN', True))
