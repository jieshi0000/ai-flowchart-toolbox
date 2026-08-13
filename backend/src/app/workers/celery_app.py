from app.core.config import get_settings
from app.workers.factory import create_celery_app

# Celery CLI loads this explicit symbol:
# celery -A app.workers.celery_app:celery_app worker -l INFO
celery_app = create_celery_app(get_settings())
