import os

from django.core.wsgi import get_wsgi_application

os.environ["IS_TOOLFORGE"] = "true"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reviewer.settings")

app = get_wsgi_application()
