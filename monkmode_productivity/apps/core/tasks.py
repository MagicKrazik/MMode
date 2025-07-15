from celery import shared_task
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Avg, Count, Q
from datetime import datetime, timedelta
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
    try:
        from apps.core.services.support_service import SupportNetworkService
        from apps.core.models import UserDailyLog
        
        users_checked = 0
        triggers_sent = 0
        
        # Get all users with recent daily logs
        recent_date = timezone.now().date() - timedelta(days=1)
        users_with_logs = User.objects.filter(
            daily_logs__log_date__gte=recent_date
        ).distinct()
        
        for user in users_with_logs:
            users_checked += 1
            if SupportNetworkService.check_mood_triggers(user):
                triggers_sent += 1
        
        logger.info(f"Checked {users_checked} users, sent {triggers_sent} mood trigger notifications")
        return f"Checked {users_checked} users, sent {triggers_sent} mood trigger notifications"
        
    except Exception as e:
        logger.error(f"Error in check_daily_mood_triggers: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def check_adherence_triggers():
    """Check all users for adherence-based support triggers"""
    try:
        from apps.core.services.support_service import SupportNetworkService
        from apps.core.models import UserDailyLog
        
        users_checked = 0
        triggers_sent = 0
        
        # Get all users with recent daily logs
        recent_date = timezone.now().date() - timedelta(days=3)
        users_with_logs = User.objects.filter(
            daily_logs__log_date__gte=recent_date
        ).distinct()
        
        for user in users_with_logs:
            users_checked += 1
            if SupportNetworkService.check_adherence_triggers(user):
                triggers_sent += 1
        
        logger.info(f"Checked {users_checked} users, sent {triggers_sent} adherence trigger notifications")
        return f"Checked {users_checked} users, sent {triggers_sent} adherence trigger notifications"
        
    except Exception as e:
        logger.error(f"Error in check_adherence_triggers: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def deliver_scheduled_letters():
    """Deliver all scheduled self letters that are due"""
    try:
        from apps.core.services.motivation_service import MotivationService
        
        letters_delivered = MotivationService.deliver_scheduled_letters()
        
        logger.info(f"Delivered {letters_delivered} scheduled letters")
        return f"Delivered {letters_delivered} scheduled letters"
        
    except Exception as e:
        logger.error(f"Error in deliver_scheduled_letters: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def generate_daily_energy_predictions():
    """Generate energy predictions for all active users"""
    try:
        from apps.core.services.energy_service import EnergyManagementService
        from apps.core.models import MonkModeGoal
        
        predictions_generated = 0
        
        # Get users with active goals
        active_users = User.objects.filter(
            monk_mode_goals__current_status='active'
        ).distinct()
        
        for user in active_users:
            try:
                predictions = EnergyManagementService.predict_energy_levels(user, hours_ahead=24)
                if predictions:
                    predictions_generated += len(predictions)
            except Exception as e:
                logger.warning(f"Failed to generate predictions for user {user.id}: {str(e)}")
                continue
        
        logger.info(f"Generated {predictions_generated} energy predictions")
        return f"Generated {predictions_generated} energy predictions"
        
    except Exception as e:
        logger.error(f"Error in generate_daily_energy_predictions: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def update_productivity_patterns():
    """Update productivity patterns for all users"""
    try:
        from apps.core.services.priority_engine import PriorityEngine
        
        patterns_updated = 0
        
        # Get users with completed activities in the last 30 days
        recent_date = timezone.now() - timedelta(days=30)
        users_with_activities = User.objects.filter(
            monk_mode_goals__periods__activities__is_completed=True,
            monk_mode_goals__periods__activities__completed_at__gte=recent_date
        ).distinct()
        
        for user in users_with_activities:
            try:
                updated = PriorityEngine.update_productivity_patterns(user)
                patterns_updated += updated
            except Exception as e:
                logger.warning(f"Failed to update patterns for user {user.id}: {str(e)}")
                continue
        
        logger.info(f"Updated {patterns_updated} productivity patterns")
        return f"Updated {patterns_updated} productivity patterns"
        
    except Exception as e:
        logger.error(f"Error in update_productivity_patterns: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def send_daily_motivation():
    """Send daily motivation to users who have it enabled"""
    try:
        from apps.core.services.motivation_service import MotivationService
        from apps.core.models import MonkModeGoal
        
        motivations_sent = 0
        
        # Get users with active goals who have motivation enabled
        users_with_motivation = User.objects.filter(
            monk_mode_goals__current_status='active',
            monk_mode_goals__motivation_reminders_enabled=True
        ).distinct()
        
        for user in users_with_motivation:
            try:
                # Check if motivation was already sent today
                today = timezone.now().date()
                # You could add a model to track daily motivation sends
                # For now, we'll send to everyone
                
                motivation = MotivationService.get_daily_motivation(user, 'morning')
                if motivation:
                    motivations_sent += 1
                    
            except Exception as e:
                logger.warning(f"Failed to send motivation to user {user.id}: {str(e)}")
                continue
        
        logger.info(f"Sent daily motivation to {motivations_sent} users")
        return f"Sent daily motivation to {motivations_sent} users"
        
    except Exception as e:
        logger.error(f"Error in send_daily_motivation: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def cleanup_old_data():
    """Clean up old data to prevent database bloat"""
    try:
        from apps.core.models import (
            AIPromptHistory, EnergyLog, EnergyPrediction, 
            SupportNotification, UserProductivityPattern
        )
        
        # Define cleanup thresholds
        old_threshold = timezone.now() - timedelta(days=365)  # 1 year
        very_old_threshold = timezone.now() - timedelta(days=730)  # 2 years
        
        cleaned_items = 0
        
        # Clean up old AI prompt history (keep 6 months)
        ai_threshold = timezone.now() - timedelta(days=180)
        old_prompts = AIPromptHistory.objects.filter(timestamp__lt=ai_threshold)
        count = old_prompts.count()
        old_prompts.delete()
        cleaned_items += count
        logger.info(f"Deleted {count} old AI prompt history records")
        
        # Clean up old energy logs (keep 1 year)
        old_energy_logs = EnergyLog.objects.filter(timestamp__lt=old_threshold)
        count = old_energy_logs.count()
        old_energy_logs.delete()
        cleaned_items += count
        logger.info(f"Deleted {count} old energy log records")
        
        # Clean up old energy predictions (keep 30 days)
        prediction_threshold = timezone.now() - timedelta(days=30)
        old_predictions = EnergyPrediction.objects.filter(created_at__lt=prediction_threshold)
        count = old_predictions.count()
        old_predictions.delete()
        cleaned_items += count
        logger.info(f"Deleted {count} old energy prediction records")
        
        # Clean up old support notifications (keep 6 months)
        notification_threshold = timezone.now() - timedelta(days=180)
        old_notifications = SupportNotification.objects.filter(sent_at__lt=notification_threshold)
        count = old_notifications.count()
        old_notifications.delete()
        cleaned_items += count
        logger.info(f"Deleted {count} old support notification records")
        
        # Clean up productivity patterns with very low sample sizes (< 3 samples and older than 3 months)
        pattern_threshold = timezone.now() - timedelta(days=90)
        low_sample_patterns = UserProductivityPattern.objects.filter(
            sample_size__lt=3,
            last_updated__lt=pattern_threshold
        )
        count = low_sample_patterns.count()
        low_sample_patterns.delete()
        cleaned_items += count
        logger.info(f"Deleted {count} low-sample productivity patterns")
        
        logger.info(f"Cleanup completed: {cleaned_items} total items removed")
        return f"Cleanup completed: {cleaned_items} total items removed"
        
    except Exception as e:
        logger.error(f"Error in cleanup_old_data: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def calculate_daily_priorities_for_active_users():
    """Calculate daily priorities for all users with active goals"""
    try:
        from apps.core.services.priority_engine import PriorityEngine
        from apps.core.models import MonkModeGoal
        
        calculations_performed = 0
        
        # Get users with active goals
        active_users = User.objects.filter(
            monk_mode_goals__current_status='active'
        ).distinct()
        
        today = timezone.now().date()
        
        for user in active_users:
            try:
                priorities = PriorityEngine.calculate_daily_priorities(user, today)
                if priorities:
                    calculations_performed += 1
                    logger.debug(f"Calculated priorities for user {user.id}: {len(priorities)} activities")
            except Exception as e:
                logger.warning(f"Failed to calculate priorities for user {user.id}: {str(e)}")
                continue
        
        logger.info(f"Calculated daily priorities for {calculations_performed} users")
        return f"Calculated daily priorities for {calculations_performed} users"
        
    except Exception as e:
        logger.error(f"Error in calculate_daily_priorities_for_active_users: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def check_milestone_achievements():
    """Check for milestone achievements and trigger celebrations"""
    try:
        from apps.core.services.motivation_service import MotivationService
        from apps.core.models import MonkModeGoal
        
        milestones_triggered = 0
        
        # Get active goals
        active_goals = MonkModeGoal.objects.filter(current_status='active')
        
        for goal in active_goals:
            try:
                # Check if goal completion percentage hit milestone
                completion = goal.completion_percentage
                
                # Check for common milestones: 25%, 50%, 75%, 100%
                milestones = [25, 50, 75, 100]
                
                for milestone in milestones:
                    if completion >= milestone:
                        # Check if we've already triggered this milestone
                        # You might want to add a model to track triggered milestones
                        # For now, we'll check completion triggers
                        
                        delivered_content = MotivationService.check_milestone_triggers(goal.user, goal)
                        if delivered_content:
                            milestones_triggered += len(delivered_content)
                            logger.info(f"Triggered milestone celebration for goal {goal.id} at {completion}%")
                        
                        break  # Only trigger one milestone per check
                        
            except Exception as e:
                logger.warning(f"Failed to check milestones for goal {goal.id}: {str(e)}")
                continue
        
        logger.info(f"Triggered {milestones_triggered} milestone celebrations")
        return f"Triggered {milestones_triggered} milestone celebrations"
        
    except Exception as e:
        logger.error(f"Error in check_milestone_achievements: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def generate_weekly_insights():
    """Generate weekly insights for users"""
    try:
        from apps.core.services.ai_service import AIService
        from apps.core.models import UserDailyLog
        
        insights_generated = 0
        
        # Check if it's Monday (good day for weekly insights)
        today = timezone.now().date()
        if today.weekday() == 0:  # Monday = 0
            
            # Get users who have logged data in the past week
            week_ago = today - timedelta(days=7)
            users_with_recent_logs = User.objects.filter(
                daily_logs__log_date__gte=week_ago
            ).distinct()
            
            for user in users_with_recent_logs:
                try:
                    insights = AIService.generate_weekly_review_insights(user)
                    if insights and "Unable to generate" not in insights:
                        insights_generated += 1
                        
                        # You could store these insights in a model or send via email
                        logger.debug(f"Generated weekly insights for user {user.id}")
                        
                except Exception as e:
                    logger.warning(f"Failed to generate insights for user {user.id}: {str(e)}")
                    continue
        
        logger.info(f"Generated weekly insights for {insights_generated} users")
        return f"Generated weekly insights for {insights_generated} users"
        
    except Exception as e:
        logger.error(f"Error in generate_weekly_insights: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def backup_user_data():
    """Backup critical user data"""
    try:
        from django.core.management import call_command
        from django.conf import settings
        import os
        
        # Create backup directory if it doesn't exist
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(backup_dir, f'monkmode_backup_{timestamp}.json')
        
        # Create database backup
        with open(backup_file, 'w') as f:
            call_command('dumpdata', '--exclude=contenttypes', '--exclude=auth.permission', stdout=f)
        
        logger.info(f"Database backup created: {backup_file}")
        
        # Clean up old backups (keep last 7 days)
        import glob
        old_backups = glob.glob(os.path.join(backup_dir, 'monkmode_backup_*.json'))
        old_backups.sort()
        
        # Keep only the most recent 7 backups
        if len(old_backups) > 7:
            for old_backup in old_backups[:-7]:
                os.remove(old_backup)
                logger.info(f"Removed old backup: {old_backup}")
        
        return f"Backup created successfully: {backup_file}"
        
    except Exception as e:
        logger.error(f"Error in backup_user_data: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def optimize_database():
    """Optimize database performance"""
    try:
        from django.db import connection
        
        optimizations_performed = 0
        
        with connection.cursor() as cursor:
            # Analyze tables for better query planning
            cursor.execute("ANALYZE;")
            optimizations_performed += 1
            
            # You could add more database-specific optimizations here
            # For PostgreSQL:
            # cursor.execute("VACUUM ANALYZE;")
            
        logger.info(f"Database optimization completed: {optimizations_performed} operations")
        return f"Database optimization completed: {optimizations_performed} operations"
        
    except Exception as e:
        logger.error(f"Error in optimize_database: {str(e)}")
        return f"Error: {str(e)}"

@shared_task
def send_weekly_summary_emails():
    """Send weekly summary emails to users"""
    try:
        from django.core.mail import send_mail
        from django.template.loader import render_to_string
        from django.conf import settings
        from apps.core.models import UserDailyLog, MonkModeGoal
        
        emails_sent = 0
        today = timezone.now().date()
        
        # Only send on Sundays
        if today.weekday() == 6:  # Sunday = 6
            week_start = today - timedelta(days=6)
            
            # Get users with activity this week
            active_users = User.objects.filter(
                Q(daily_logs__log_date__gte=week_start) |
                Q(monk_mode_goals__current_status='active')
            ).distinct()
            
            for user in active_users:
                try:
                    # Gather weekly data
                    weekly_logs = UserDailyLog.objects.filter(
                        user=user,
                        log_date__gte=week_start
                    )
                    
                    if weekly_logs.exists():
                        # Calculate weekly metrics
                        avg_mood = weekly_logs.aggregate(avg=Avg('mood_rating'))['avg'] or 0
                        avg_adherence = weekly_logs.aggregate(avg=Avg('adherence_score'))['avg'] or 0
                        
                        # Generate weekly summary email
                        subject = f"Your MonkMode Weekly Summary - {week_start.strftime('%B %d')}"
                        
                        html_message = render_to_string('emails/weekly_summary.html', {
                            'user': user,
                            'week_start': week_start,
                            'week_end': today,
                            'weekly_logs': weekly_logs,
                            'avg_mood': round(avg_mood, 1),
                            'avg_adherence': round(avg_adherence, 1),
                            'days_logged': weekly_logs.count(),
                        })
                        
                        send_mail(
                            subject=subject,
                            message=f"Your weekly summary is ready! Average mood: {avg_mood:.1f}/5, Average adherence: {avg_adherence:.1f}/10",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[user.email],
                            html_message=html_message,
                            fail_silently=False
                        )
                        
                        emails_sent += 1
                        logger.debug(f"Sent weekly summary to user {user.id}")
                        
                except Exception as e:
                    logger.warning(f"Failed to send weekly summary to user {user.id}: {str(e)}")
                    continue
        
        logger.info(f"Sent weekly summary emails to {emails_sent} users")
        return f"Sent weekly summary emails to {emails_sent} users"
        
    except Exception as e:
        logger.error(f"Error in send_weekly_summary_emails: {str(e)}")
        return f"Error: {str(e)}"