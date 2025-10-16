import requests
import pywikibot
import logging

from django.core.management.base import BaseCommand
from pywikibot.exceptions import NoUsernameError
from pywikibot.data.superset import SupersetQuery

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Tests the standard username and password login using the Pywikibot framework to superset.'

    def handle(self, *args, **options):
        site=pywikibot.Site('meta', 'meta')        

        try:
            site.login()
        
            if site.logged_in():
                logger.info(f"✅ Successfully logged into MediaWiki API as {site.user()}.")

                superset = SupersetQuery(site=site)

                try:
                    superset.login()

                    if(superset.connected):
                        logger.info(f"✅ User {site.user()} Connected to Superset successfully.")

                except requests.TooManyRedirects as e:
                    logger.error(f"❌ Superset Oauth failed, {e}. ")
                    logger.info(f"⚠️ Ensure you are authenticated with main account as superset does not support botpassword auth.")

        except NoUsernameError as e:

             logger.error(f"❌ MediaWiki Login Failed: {e}")
