"""
Updated tests that pass category_namespaces parameter.
Replace your existing test file with this version.
"""

from django.test import TestCase
from reviews.autoreview import _count_categories, _is_redirect, _removes_all_categories


class TestRemoveAllCategories(TestCase):
    """Test cases for detecting removal of all categories from articles."""

    def test_removes_all_categories_blocks_autoreview(self):
        """Test that removing all categories prevents auto-review."""
        old_text = """
This is an article with content.

[[Category:Example]]
[[Category:Another category]]
"""
        new_text = """
This is an article with content.
"""

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category"]
        self.assertTrue(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_removes_some_categories_allows_autoreview(self):
        """Test that removing some (but not all) categories allows auto-review."""
        old_text = """
This is an article with content.

[[Category:Example]]
[[Category:Another category]]
[[Category:Third category]]
"""
        new_text = """
This is an article with content.

[[Category:Example]]
"""

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category"]
        self.assertFalse(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_no_categories_initially_allows_autoreview(self):
        """Test that pages without categories can be auto-reviewed."""
        old_text = """
This is an article without categories.
"""
        new_text = """
This is an article without categories, now edited.
"""

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category"]
        self.assertFalse(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_redirect_with_category_removal_allows_autoreview(self):
        """Test that converting to redirect with category removal allows auto-review."""
        old_text = """
This is an article with content.

[[Category:Example]]
[[Category:Another category]]
"""
        new_text = "#REDIRECT [[Target Page]]"

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category"]
        self.assertFalse(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_redirect_finnish_magic_word(self):
        """Test Finnish redirect magic word."""
        old_text = """
Artikkeli sisältöä.

[[Luokka:Esimerkki]]
"""
        new_text = "#OHJAUS [[Kohde]]"

        redirect_aliases = ["#OHJAUS", "#REDIRECT"]
        category_namespaces = ["Luokka", "Category"]
        self.assertFalse(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_adds_categories_allows_autoreview(self):
        """Test that adding categories allows auto-review."""
        old_text = """
This is an article with content.
"""
        new_text = """
This is an article with content.

[[Category:New category]]
"""

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category"]
        self.assertFalse(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_case_insensitive_category_detection(self):
        """Test that category detection is case-insensitive."""
        old_text = """
Article content.

[[category:Example]]
[[CATEGORY:Another]]
"""
        new_text = """
Article content.
"""

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category"]
        self.assertTrue(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_finnish_category_namespace(self):
        """Test Finnish category namespace (Luokka)."""
        old_text = """
Artikkeli.

[[Luokka:Esimerkki]]
[[Luokka:Toinen]]
"""
        new_text = """
Artikkeli.
"""

        redirect_aliases = ["#OHJAUS"]
        category_namespaces = ["Luokka"]
        self.assertTrue(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_mixed_language_categories(self):
        """Test mixed English and Finnish categories."""
        old_text = """
Article.

[[Category:Example]]
[[Luokka:Esimerkki]]
"""
        new_text = """
Article.
"""

        redirect_aliases = ["#REDIRECT"]
        category_namespaces = ["Category", "Luokka"]
        self.assertTrue(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_german_category_namespace(self):
        """Test German category namespace (Kategorie)."""
        old_text = """
Artikel.

[[Kategorie:Beispiel]]
"""
        new_text = """
Artikel.
"""

        redirect_aliases = ["#WEITERLEITUNG"]
        category_namespaces = ["Kategorie"]
        self.assertTrue(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))

    def test_polish_category_namespace(self):
        """Test Polish category namespace (Kategoria)."""
        old_text = """
Artykuł.

[[Kategoria:Przykład]]
"""
        new_text = """
Artykuł.
"""

        redirect_aliases = ["#PATRZ"]
        category_namespaces = ["Kategoria"]
        self.assertTrue(_removes_all_categories(old_text, new_text, redirect_aliases, category_namespaces))


class TestCountCategories(TestCase):
    """Test cases for counting categories in wikitext."""

    def test_count_single_category(self):
        """Test counting a single category."""
        text = "[[Category:Example]]"
        self.assertEqual(_count_categories(text, ["Category"]), 1)

    def test_count_multiple_categories(self):
        """Test counting multiple categories."""
        text = """
[[Category:First]]
[[Category:Second]]
[[Category:Third]]
"""
        self.assertEqual(_count_categories(text, ["Category"]), 3)

    def test_count_finnish_categories(self):
        """Test counting Finnish categories."""
        text = """
[[Luokka:Ensimmäinen]]
[[Luokka:Toinen]]
"""
        self.assertEqual(_count_categories(text, ["Luokka"]), 2)

    def test_count_german_categories(self):
        """Test counting German categories."""
        text = "[[Kategorie:Beispiel]]"
        self.assertEqual(_count_categories(text, ["Kategorie"]), 1)

    def test_count_polish_categories(self):
        """Test counting Polish categories."""
        text = "[[Kategoria:Przykład]]"
        self.assertEqual(_count_categories(text, ["Kategoria"]), 1)

    def test_count_mixed_case(self):
        """Test counting with mixed case."""
        text = """
[[category:Lower]]
[[CATEGORY:Upper]]
[[Category:Mixed]]
"""
        self.assertEqual(_count_categories(text, ["Category"]), 3)

    def test_count_no_categories(self):
        """Test counting when no categories present."""
        text = "Just some text without categories."
        self.assertEqual(_count_categories(text, ["Category"]), 0)

    def test_count_with_multiple_namespaces(self):
        """Test counting with multiple namespace aliases."""
        text = """
[[Category:English]]
[[Luokka:Finnish]]
[[Kategorie:German]]
"""
        namespaces = ["Category", "Luokka", "Kategorie"]
        self.assertEqual(_count_categories(text, namespaces), 3)

    def test_count_ignores_unknown_namespaces(self):
        """Test that unknown namespaces are not counted."""
        text = """
[[Category:Known]]
[[UnknownNamespace:Ignored]]
"""
        self.assertEqual(_count_categories(text, ["Category"]), 1)

    def test_count_categories_with_colons_in_name(self):
        """Test counting categories with colons in the name."""
        text = "[[Category:Example:Subcategory]]"
        self.assertEqual(_count_categories(text, ["Category"]), 1)

    def test_category_with_linebreak(self):
        """Test category link with line break inside."""
        text = """[[Category:Example
with linebreak]]"""
        self.assertEqual(_count_categories(text, ["Category"]), 1)

    def test_category_with_whitespace_around_colon(self):
        """Test category with extra whitespace."""
        text = "[[ Category : Example ]]"
        self.assertEqual(_count_categories(text, ["Category"]), 1)

    def test_empty_namespace_list(self):
        """Test with empty namespace list."""
        text = "[[Category:Example]]"
        self.assertEqual(_count_categories(text, []), 0)


class TestIsRedirect(TestCase):
    """Test cases for redirect detection."""

    def test_basic_english_redirect(self):
        """Test basic English redirect."""
        text = "#REDIRECT [[Target Page]]"
        self.assertTrue(_is_redirect(text, ["#REDIRECT"]))

    def test_finnish_redirect(self):
        """Test Finnish redirect."""
        text = "#OHJAUS [[Kohdesivu]]"
        self.assertTrue(_is_redirect(text, ["#OHJAUS"]))

    def test_german_redirect(self):
        """Test German redirect."""
        text = "#WEITERLEITUNG [[Zielseite]]"
        self.assertTrue(_is_redirect(text, ["#WEITERLEITUNG"]))

    def test_polish_redirect(self):
        """Test Polish redirect."""
        text = "#PATRZ [[Strona docelowa]]"
        self.assertTrue(_is_redirect(text, ["#PATRZ"]))

    def test_redirect_with_whitespace(self):
        """Test redirect with extra whitespace."""
        text = "#  REDIRECT   [[Target]]"
        self.assertTrue(_is_redirect(text, ["#REDIRECT"]))

    def test_redirect_case_insensitive(self):
        """Test that redirect detection is case-insensitive."""
        text = "#redirect [[Target]]"
        self.assertTrue(_is_redirect(text, ["#REDIRECT"]))

    def test_not_a_redirect(self):
        """Test that regular content is not detected as redirect."""
        text = "This is regular article content."
        self.assertFalse(_is_redirect(text, ["#REDIRECT"]))

    def test_redirect_in_middle_of_text(self):
        """Test that redirect must be at the beginning."""
        text = "Some text\n#REDIRECT [[Target]]"
        self.assertFalse(_is_redirect(text, ["#REDIRECT"]))

    def test_empty_text(self):
        """Test empty text is not a redirect."""
        text = ""
        self.assertFalse(_is_redirect(text, ["#REDIRECT"]))

    def test_multiple_aliases(self):
        """Test with multiple redirect aliases."""
        text = "#OHJAUS [[Target]]"
        aliases = ["#REDIRECT", "#OHJAUS", "#WEITERLEITUNG"]
        self.assertTrue(_is_redirect(text, aliases))