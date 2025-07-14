import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'monkmode_productivity.settings')

app = Celery('monkmode_productivity')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat Schedule for periodic tasks
app.conf.beat_schedule = {
    'check-mood-triggers-daily': {
        'task': 'apps.core.tasks.check_daily_mood_triggers',
        'schedule': 60.0 * 60.0 * 24.0,  # Every 24 hours
    },
    'check-adherence-triggers': {
        'task': 'apps.core.tasks.check_adherence_triggers',
        'schedule': 60.0 * 60.0 * 6.0,  # Every 6 hours
    },
    'deliver-scheduled-letters': {
        'task': 'apps.core.tasks.deliver_scheduled_letters',
        'schedule': 60.0 * 60.0,  # Every hour
    },
    'generate-energy-predictions': {
        'task': 'apps.core.tasks.generate_daily_energy_predictions',
        'schedule': 60.0 * 60.0 * 6.0,  # Every 6 hours
    },
    'update-productivity-patterns': {
        'task': 'apps.core.tasks.update_productivity_patterns',
        'schedule': 60.0 * 60.0 * 24.0,  # Every 24 hours
    },
    'send-daily-motivation': {
        'task': 'apps.core.tasks.send_daily_motivation',
        'schedule': 60.0 * 30.0,  # Every 30 minutes
    },
    'cleanup-old-data': {
        'task': 'apps.core.tasks.cleanup_old_data',
        'schedule': 60.0 * 60.0 * 24.0 * 7.0,  # Every week
    },
    'calculate-daily-priorities': {
        'task': 'apps.core.tasks.calculate_daily_priorities_for_active_users',
        'schedule': 60.0 * 60.0 * 2.0,  # Every 2 hours
    },
    'check-milestone-achievements': {
        'task': 'apps.core.tasks.check_milestone_achievements',
        'schedule': 60.0 * 60.0 * 4.0,  # Every 4 hours
    },
    'generate-weekly-insights': {
        'task': 'apps.core.tasks.generate_weekly_insights',
        'schedule': 60.0 * 60.0 * 24.0,  # Every 24 hours
    },
}

app.conf.timezone = 'UTC'

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')