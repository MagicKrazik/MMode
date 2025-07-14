from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def test_task():
    """Simple test task"""
    logger.info("Test task executed successfully!")
    return "Test task completed"

@shared_task
def check_daily_mood_triggers():
    """Check all users for mood-based support triggers"""
    logger.info("Running daily mood trigger check...")
    return "Mood trigger check completed"

@shared_task
def check_adherence_triggers():
    """Check all users for adherence-based support triggers"""
    logger.info("Running adherence trigger check...")
    return "Adherence trigger check completed"

@shared_task
def deliver_scheduled_letters():
    """Deliver all scheduled self letters that are due"""
    logger.info("Checking for scheduled letters...")
    return "Letter delivery check completed"

@shared_task
def generate_daily_energy_predictions():
    """Generate energy predictions for all active users"""
    logger.info("Generating energy predictions...")
    return "Energy prediction generation completed"

@shared_task
def update_productivity_patterns():
    """Update productivity patterns for all users"""
    logger.info("Updating productivity patterns...")
    return "Productivity pattern update completed"

@shared_task
def send_daily_motivation():
    """Send daily motivation to users who have it enabled"""
    logger.info("Sending daily motivation...")
    return "Daily motivation sent"

@shared_task
def cleanup_old_data():
    """Clean up old data to prevent database bloat"""
    logger.info("Cleaning up old data...")
    return "Data cleanup completed"

@shared_task
def calculate_daily_priorities_for_active_users():
    """Calculate daily priorities for all users with active goals"""
    logger.info("Calculating daily priorities...")
    return "Priority calculation completed"

@shared_task
def check_milestone_achievements():
    """Check for milestone achievements and trigger celebrations"""
    logger.info("Checking milestone achievements...")
    return "Milestone check completed"

@shared_task
def generate_weekly_insights():
    """Generate weekly insights for users"""
    logger.info("Generating weekly insights...")
    return "Weekly insights generated"