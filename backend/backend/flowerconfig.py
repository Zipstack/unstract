# Flower is a real-time web based monitor and administration tool
#  for Celery. It’s under active development,
# but is already an essential tool.
from django.conf import settings

# Broker URL
BROKER_URL = settings.CELERY_BROKER_URL

# Flower web port
PORT = 5555

# Enable basic authentication (when required)
# basic_auth = {
#     'username': 'password'
# }
