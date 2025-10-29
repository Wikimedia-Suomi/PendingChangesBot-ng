import logging
from datetime import datetime

import pywikibot
from pywikibot.data.api import Request

logger = logging.getLogger(__name__)

_LIVING_CATEGORIES_CACHE = {}


def _get_living_category(lang_code: str) -> str:
    """Get localized 'Living people' category name for a language."""
    if lang_code in _LIVING_CATEGORIES_CACHE:
        return _LIVING_CATEGORIES_CACHE[lang_code]

    if not _LIVING_CATEGORIES_CACHE:
        try:
            site = pywikibot.Site("wikidata", "wikidata")
            req = Request(
                site=site,
                parameters={
                    "action": "wbgetentities",
                    "sites": "enwiki",
                    "titles": "Category:Living_people",
                    "props": "sitelinks",
                },
            )
            data = req.submit()
            entity = next(iter(data["entities"].values()))
            sitelinks = entity["sitelinks"]

            for wiki_code, sitelink_data in sitelinks.items():
                title = sitelink_data["title"]
                category_name = title.split(":", 1)[1] if ":" in title else title
                lang = wiki_code.replace("wiki", "")
                _LIVING_CATEGORIES_CACHE[lang] = category_name

            logger.info(f"Loaded {len(_LIVING_CATEGORIES_CACHE)} living category translations")
        except Exception as e:
            logger.error(f"Failed to load living categories: {e}")

    return _LIVING_CATEGORIES_CACHE.get(lang_code)


def _check_by_category(page, lang_code: str) -> bool:
    """Check if page has 'Living people' category."""
    living_category = _get_living_category(lang_code)
    if not living_category:
        return False

    try:
        for cat in page.categories():
            cat_name = cat.title(with_ns=False).replace("_", " ").lower()
            if cat_name == living_category.replace("_", " ").lower():
                return True
    except Exception as e:
        logger.warning(f"Error checking categories: {e}")

    return False


def _check_by_wikidata(page) -> bool:
    """Check if person is human and living via Wikidata (P31=Q5, no P570, P569<130y)."""
    try:
        item = pywikibot.ItemPage.fromPage(page)
        item.get()
    except Exception:
        return False

    if "P31" not in item.claims:
        return False

    is_human = any(c.getTarget().id == "Q5" for c in item.claims["P31"])
    if not is_human:
        return False

    if "P570" in item.claims:
        return False

    if "P569" in item.claims:
        try:
            birth = item.claims["P569"][0].getTarget()
            if birth.year:
                age = datetime.now().year - birth.year
                return age < 130
        except Exception:
            return True

    return True


def is_living_person(lang: str, article_title: str) -> bool:
    """Check if Wikipedia article is about a living person. Pass language code as lang."""
    try:
        site = pywikibot.Site(lang, "wikipedia")
        page = pywikibot.Page(site, article_title)

        if not page.exists():
            return False
    except Exception as e:
        logger.error(f"Error accessing page: {e}")
        return False

    if _check_by_category(page, lang):
        return True

    if _check_by_wikidata(page):
        return True

    return False
