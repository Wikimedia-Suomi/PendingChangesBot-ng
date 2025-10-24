import logging

import pywikibot
import requests
from django.core.management.base import BaseCommand
from pywikibot.data.superset import SupersetQuery
from pywikibot.exceptions import NoUsernameError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Tests the standard username and password login using the Pywikibot framework to superset."
    )

    def handle(self, *args, **options):
        site = pywikibot.Site("meta", "meta")

        try:
            site.login()

            if site.logged_in():
                logger.info(f"✅ Successfully logged into MediaWiki API as {site.user()}.")

                try:
                    superset = SupersetQuery(site=site)
                    superset.login()

                    if superset.connected:
                        logger.info(f"✅ User {site.user()} Connected to Superset successfully.")

                except requests.TooManyRedirects as e:
                    logger.error(f"❌ Superset Oauth failed, {e}. ")
                    logger.info(
                        "⚠️ Ensure you are authenticated "
                        "with main account as superset does not support botpassword auth."
                    )
                except NoUsernameError as e:
                    logger.info(
                        "⚠️ Try Sign in with **MediaWiki** to Superset: "
                        "https://superset.wmcloud.org/login/"
                    )
                    logger.error(f"❌ Superset Oauth failed, {e}. ")
        except NoUsernameError as e:
            logger.error(f"❌ MediaWiki Login Failed: {e}")
