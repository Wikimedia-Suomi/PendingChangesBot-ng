from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import Client, TestCase
from django.urls import reverse

from reviews.models import (
    EditorProfile,
    PendingPage,
    PendingRevision,
    Wiki,
    WikiConfiguration,
)


class RedirectConversionTests(TestCase):
    """Tests for redirect conversion autoreview functionality."""

    def setUp(self):
        self.client = Client()
        self.wiki = Wiki.objects.create(
            name="Test Wiki",
            code="test",
            family="wikipedia",
            api_endpoint="https://test.wikipedia.org/w/api.php",
        )
        WikiConfiguration.objects.create(wiki=self.wiki)

    @mock.patch("reviews.models.pywikibot.Site")
    def test_article_to_redirect_conversion_should_block(self, mock_site):
        """Article-to-redirect conversion by autopatrolled user should be blocked."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1220095,
            title="Pekingin tekninen instituutti",
            stable_revid=22754221,
        )

        old_article_wikitext = """
'''Pekingin tekninen instituutti''' on kiinalainen yliopisto Pekingissä.

Se keskittyy luonnontieteisiin ja teknologiaan.
Koulutusta tarjotaan englanniksi ja kiinaksi.

Yliopistossa on kaksi pääkirjastoa, yhteensä 46 000 neliömetriä.

[[Category:Kiinalaiset yliopistot]]
[[Category:Pekingin yliopistot]]
"""
        new_redirect_wikitext = "#OHJAUS [[Pekingin teknillinen korkeakoulu]]"

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.requests: list[dict] = []
                self.wikitext_call_count = 0

            def simple_request(self, **kwargs):
                self.requests.append(kwargs)

                # Check if this is a request for magic words
                if kwargs.get("meta") == "siteinfo" and kwargs.get("siprop") == "magicwords":
                    return FakeRequest({
                        "query": {
                            "magicwords": [
                                {
                                    "name": "redirect",
                                    "aliases": ["#OHJAUS", "#UUDELLEENOHJAUS", "#REDIRECT"]
                                }
                            ]
                        }
                    })

                # Otherwise, it's a wikitext request
                if self.wikitext_call_count == 0:
                    self.wikitext_call_count += 1
                    return FakeRequest({
                        "query": {
                            "pages": [{
                                "revisions": [{
                                    "slots": {
                                        "main": {"content": old_article_wikitext}
                                    }
                                }]
                            }]
                        }
                    })
                else:
                    return FakeRequest({
                        "query": {
                            "pages": [{
                                "revisions": [{
                                    "slots": {
                                        "main": {"content": new_redirect_wikitext}
                                    }
                                }]
                            }]
                        }
                    })

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        PendingRevision.objects.create(
            page=page,
            revid=22754221,
            parentid=None,
            user_name="OriginalAuthor",
            user_id=99999,
            timestamp=datetime.now(timezone.utc) - timedelta(days=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(days=1),
            sha1="oldsha",
            comment="Original article",
            change_tags=[],
            wikitext=old_article_wikitext,
            categories=[],
            superset_data={},
        )

        PendingRevision.objects.create(
            page=page,
            revid=23567438,
            parentid=22754221,
            user_name="RegularUser",
            user_id=12345,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="abc123",
            comment="f: muutettu ohjaussivuksi",
            change_tags=[],
            wikitext=new_redirect_wikitext,
            categories=[],
            superset_data={
                "user_groups": ["user", "autopatrolled"],
                "rc_bot": False,
            },
        )

        EditorProfile.objects.create(
            wiki=self.wiki,
            username="RegularUser",
            usergroups=["user", "autopatrolled"],
            is_autopatrolled=True,
            is_autoreviewed=False,
            is_bot=False,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result = data["results"][0]

        self.assertEqual(
            result["decision"]["status"],
            "blocked",
            "Article-to-redirect conversions should be blocked for autopatrolled-only users"
        )

    @mock.patch("reviews.models.pywikibot.Site")
    def test_redirect_to_redirect_edit_should_not_block(self, mock_site):
        """Redirect-to-redirect edit should not block based on this rule."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=888,
            title="Existing Redirect",
            stable_revid=50,
        )

        old_redirect = "#OHJAUS [[Old Target]]"
        new_redirect = "#OHJAUS [[New Target]]"

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.requests: list[dict] = []
                self.wikitext_call_count = 0

            def simple_request(self, **kwargs):
                self.requests.append(kwargs)

                # Check if this is a request for magic words
                if kwargs.get("meta") == "siteinfo" and kwargs.get("siprop") == "magicwords":
                    return FakeRequest({
                        "query": {
                            "magicwords": [
                                {
                                    "name": "redirect",
                                    "aliases": ["#OHJAUS", "#UUDELLEENOHJAUS", "#REDIRECT"]
                                }
                            ]
                        }
                    })

                # Otherwise, it's a wikitext request
                if self.wikitext_call_count == 0:
                    self.wikitext_call_count += 1
                    return FakeRequest({
                        "query": {
                            "pages": [{
                                "revisions": [{
                                    "slots": {"main": {"content": old_redirect}}
                                }]
                            }]
                        }
                    })
                return FakeRequest({
                    "query": {
                        "pages": [{
                            "revisions": [{
                                "slots": {"main": {"content": new_redirect}}
                            }]
                        }]
                    }
                })

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        PendingRevision.objects.create(
            page=page,
            revid=50,
            parentid=None,
            user_name="PreviousEditor",
            user_id=776,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="oldhash",
            comment="Initial redirect",
            change_tags=[],
            wikitext=old_redirect,
            categories=[],
            superset_data={},
        )

        PendingRevision.objects.create(
            page=page,
            revid=60,
            parentid=50,
            user_name="Editor",
            user_id=777,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(minutes=30),
            sha1="hash",
            comment="Update redirect target",
            change_tags=[],
            wikitext=new_redirect,
            categories=[],
            superset_data={"user_groups": ["user", "autopatrolled"]},
        )

        EditorProfile.objects.create(
            wiki=self.wiki,
            username="Editor",
            usergroups=["user", "autopatrolled"],
            is_autopatrolled=True,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")

    @mock.patch("reviews.models.pywikibot.Site")
    def test_article_to_redirect_by_autoreviewed_user_should_allow(self, mock_site):
        """Article-to-redirect by auto-reviewed user should allow."""
        config = self.wiki.configuration
        config.auto_approved_groups = ["autoreviewer"]
        config.save(update_fields=["auto_approved_groups"])

        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=999,
            title="Test Article",
            stable_revid=100,
        )

        old_article = "Full article content [[Category:Test]]"
        new_redirect = "#OHJAUS [[Another Page]]"

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.requests: list[dict] = []
                self.wikitext_call_count = 0

            def simple_request(self, **kwargs):
                self.requests.append(kwargs)

                # Check if this is a request for magic words
                if kwargs.get("meta") == "siteinfo" and kwargs.get("siprop") == "magicwords":
                    return FakeRequest({
                        "query": {
                            "magicwords": [
                                {
                                    "name": "redirect",
                                    "aliases": ["#OHJAUS", "#UUDELLEENOHJAUS", "#REDIRECT"]
                                }
                            ]
                        }
                    })

                # Otherwise, it's a wikitext request
                if self.wikitext_call_count == 0:
                    self.wikitext_call_count += 1
                    return FakeRequest({
                        "query": {
                            "pages": [{
                                "revisions": [{
                                    "slots": {"main": {"content": old_article}}
                                }]
                            }]
                        }
                    })
                return FakeRequest({
                    "query": {
                        "pages": [{
                            "revisions": [{
                                "slots": {"main": {"content": new_redirect}}
                            }]
                        }]
                    }
                })

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        PendingRevision.objects.create(
            page=page,
            revid=200,
            parentid=100,
            user_name="TrustedUser",
            user_id=999,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash",
            comment="Redirect",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={"user_groups": ["user", "autoreviewer"]},
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")

    @mock.patch("reviews.models.pywikibot.Site")
    def test_localized_redirect_keywords(self, mock_site):
        """Localized redirect keywords should be recognized."""
        page = PendingPage.objects.create(
            wiki=self.wiki,
            pageid=1111,
            title="Another Article",
            stable_revid=500,
        )

        old_article = "This is a full article [[Category:Articles]]"
        new_redirect = "#OHJAUS [[Target Page]]"

        class FakeRequest:
            def __init__(self, data):
                self._data = data

            def submit(self):
                return self._data

        class FakeSite:
            def __init__(self):
                self.requests: list[dict] = []
                self.wikitext_call_count = 0

            def simple_request(self, **kwargs):
                self.requests.append(kwargs)

                # Check if this is a request for magic words
                if kwargs.get("meta") == "siteinfo" and kwargs.get("siprop") == "magicwords":
                    return FakeRequest({
                        "query": {
                            "magicwords": [
                                {
                                    "name": "redirect",
                                    "aliases": ["#OHJAUS", "#UUDELLEENOHJAUS", "#REDIRECT"]
                                }
                            ]
                        }
                    })

                # Otherwise, it's a wikitext request
                if self.wikitext_call_count == 0:
                    self.wikitext_call_count += 1
                    return FakeRequest({
                        "query": {
                            "pages": [{
                                "revisions": [{
                                    "slots": {"main": {"content": old_article}}
                                }]
                            }]
                        }
                    })
                return FakeRequest({
                    "query": {
                        "pages": [{
                            "revisions": [{
                                "slots": {"main": {"content": new_redirect}}
                            }]
                        }]
                    }
                })

        fake_site = FakeSite()
        mock_site.return_value = fake_site

        PendingRevision.objects.create(
            page=page,
            revid=600,
            parentid=500,
            user_name="AutoreviewedEditor",
            user_id=8888,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            fetched_at=datetime.now(timezone.utc),
            age_at_fetch=timedelta(hours=1),
            sha1="hash999",
            comment="Converting to redirect",
            change_tags=[],
            wikitext="",
            categories=[],
            superset_data={"user_groups": ["user", "autoreviewer"]},
        )

        # Create profile with is_autoreviewed=True (default rights)
        EditorProfile.objects.create(
            wiki=self.wiki,
            username="AutoreviewedEditor",
            usergroups=["user", "autoreviewer"],
            is_autopatrolled=False,
            is_autoreviewed=True,  # Has autoreview default right
            is_bot=False,
        )

        url = reverse("api_autoreview", args=[self.wiki.pk, page.pageid])
        response = self.client.post(url)

        result = response.json()["results"][0]
        self.assertEqual(result["decision"]["status"], "approve")

    def test_case_insensitive_redirect_keywords(self):
        """Case insensitive redirect keywords should be recognized."""
        from reviews.autoreview import _is_redirect

        aliases = ["#REDIRECT", "#OHJAUS"]

        self.assertTrue(_is_redirect("#REDIRECT [[Target]]", aliases))
        self.assertTrue(_is_redirect("#Redirect [[Target]]", aliases))
        self.assertTrue(_is_redirect("#redirect [[target]]", aliases))
        self.assertTrue(_is_redirect("#ReDiRecT [[target]]", aliases))
        self.assertTrue(_is_redirect("#OHJAUS [[Kohde]]", aliases))
        self.assertTrue(_is_redirect("#ohjaus [[Kohde]]", aliases))
        self.assertTrue(_is_redirect("#Ohjaus [[Kohde]]", aliases))
        self.assertTrue(_is_redirect("#REDIRECT  [[Target]]", aliases))
        self.assertTrue(_is_redirect("# REDIRECT [[Target]]", aliases))
        self.assertTrue(_is_redirect("#REDIRECT [[Help:Page#Section]]", aliases))
        self.assertTrue(_is_redirect("#REDIRECT [[Target]]\n[[Category:Test]]", aliases))
        self.assertTrue(_is_redirect("#UUDELLEENOHJAUS [[Kohde]]", ["#UUDELLEENOHJAUS"]))

        self.assertFalse(_is_redirect("  #REDIRECT [[Target]]", aliases))
        self.assertFalse(_is_redirect("\n#REDIRECT [[Target]]", aliases))
        self.assertFalse(_is_redirect(" \t#REDIRECT [[Target]]", aliases))
        self.assertFalse(_is_redirect("\n\n#REDIRECT [[Target]]", aliases))
        self.assertFalse(_is_redirect("Text #REDIRECT [[Target]]", aliases))
        self.assertFalse(_is_redirect("#REDIRECT [[Target", aliases))
        self.assertFalse(_is_redirect("#REDIRECT [[", aliases))
        self.assertFalse(_is_redirect("#REDIRECT \n[[Target]]", aliases))
        self.assertFalse(_is_redirect("#REDIRECT[[s\nource]]", aliases))
        self.assertFalse(_is_redirect("", aliases))
        self.assertFalse(_is_redirect("#REDIRECT", aliases))
        self.assertFalse(_is_redirect("Normal article content", aliases))
