from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from apps.core.models import SupportContact, SupportNotification, UserDailyLog
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SupportNetworkService:
    
    @staticmethod
    def check_mood_triggers(user):
        """Check if user's mood rating warrants support notification"""
        try:
            # Get last 3 days of mood ratings
            recent_logs = UserDailyLog.objects.filter(
                user=user,
                log_date__gte=timezone.now().date() - timedelta(days=3),
                mood_rating__isnull=False
            ).order_by('-log_date')
            
            if not recent_logs.exists():
                return False
            
            # Check for concerning patterns
            latest_mood = recent_logs.first().mood_rating
            avg_mood = sum(log.mood_rating for log in recent_logs) / len(recent_logs)
            
            # Trigger if latest mood is 2 or below, or average is below 2.5
            if latest_mood <= 2 or avg_mood <= 2.5:
                SupportNetworkService.trigger_support_notification(
                    user, 'mood_low', {
                        'latest_mood': latest_mood,
                        'average_mood': avg_mood,
                        'days_checked': len(recent_logs)
                    }
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking mood triggers for user {user.id}: {str(e)}")
            return False
    
    @staticmethod
    def check_adherence_triggers(user):
        """Check if user's adherence warrants support notification"""
        try:
            # Get last 3 days of adherence scores
            recent_logs = UserDailyLog.objects.filter(
                user=user,
                log_date__gte=timezone.now().date() - timedelta(days=3),
                adherence_score__isnull=False
            ).order_by('-log_date')
            
            if not recent_logs.exists():
                return False
            
            avg_adherence = sum(log.adherence_score for log in recent_logs) / len(recent_logs)
            
            # Trigger if average adherence is below 6
            if avg_adherence <= 6:
                SupportNetworkService.trigger_support_notification(
                    user, 'adherence_drop', {
                        'average_adherence': avg_adherence,
                        'days_checked': len(recent_logs)
                    }
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking adherence triggers for user {user.id}: {str(e)}")
            return False
    
    @staticmethod
    def trigger_support_notification(user, trigger_type, context_data=None):
        """Send notification to user's support network"""
        try:
            # Get active support contacts
            support_contacts = SupportContact.objects.filter(
                user=user,
                is_active=True
            )
            
            if not support_contacts.exists():
                logger.info(f"No support contacts found for user {user.id}")
                return False
            
            # Check if we've already sent a notification for this trigger recently
            recent_notifications = SupportNotification.objects.filter(
                user=user,
                trigger_type=trigger_type,
                sent_at__gte=timezone.now() - timedelta(hours=24)
            )
            
            if recent_notifications.exists():
                logger.info(f"Recent notification already sent for {trigger_type} to user {user.id}")
                return False
            
            # Generate message based on trigger type
            message_template = SupportNetworkService._get_message_template(trigger_type, context_data)
            
            notifications_sent = 0
            for contact in support_contacts:
                # Check contact's notification preferences
                preferences = contact.notification_preferences or {}
                if preferences.get(trigger_type, True):  # Default to True if not specified
                    
                    # Create notification record
                    notification = SupportNotification.objects.create(
                        user=user,
                        support_contact=contact,
                        trigger_type=trigger_type,
                        message_template=message_template,
                        sent_at=timezone.now()
                    )
                    
                    # Send email
                    success = SupportNetworkService._send_support_email(
                        contact, user, message_template, trigger_type, context_data
                    )
                    
                    if success:
                        notifications_sent += 1
                    else:
                        # Delete notification record if email failed
                        notification.delete()
            
            logger.info(f"Sent {notifications_sent} support notifications for user {user.id}")
            return notifications_sent > 0
            
        except Exception as e:
            logger.error(f"Error triggering support notification: {str(e)}")
            return False
    
    @staticmethod
    def _get_message_template(trigger_type, context_data):
        """Generate appropriate message based on trigger type"""
        if not context_data:
            context_data = {}
            
        templates = {
            'mood_low': f"""
            Hi there! 👋
            
            I wanted to reach out because {context_data.get('user_name', 'your friend')} has been going through 
            a challenging time with their Monk Mode journey. Their mood has dipped recently 
            (current: {context_data.get('latest_mood', 'N/A')}/5), and they could really use some encouragement.
            
            A quick message, call, or even just letting them know you're thinking of them could make 
            a huge difference right now. Sometimes the simplest gestures have the biggest impact! 💙
            
            Thanks for being part of their support network!
            """,
            
            'adherence_drop': f"""
            Hello! 👋
            
            {context_data.get('user_name', 'Your friend')} has been struggling to stick to their Monk Mode 
            schedule lately. Their adherence has dropped to {context_data.get('average_adherence', 'N/A')}/10 
            over the past few days.
            
            This is totally normal - everyone goes through rough patches! But a little encouragement 
            from someone who cares could help them get back on track. Maybe share a success story, 
            remind them why they started, or just check in to see how they're doing.
            
            Your support means the world to them! 🌟
            """,
            
            'missed_activities': """
            Hey! 👋
            
            Just a heads up that your friend has been missing some important activities in their 
            Monk Mode schedule. Life happens, and everyone needs a reminder sometimes that it's 
            okay to stumble as long as we get back up!
            
            Maybe reach out and see if there's anything specific they're struggling with, or just 
            remind them that you believe in their ability to achieve their goals.
            
            Thanks for being awesome! 💪
            """,
            
            'emergency': """
            URGENT: Support Needed 🚨
            
            Your friend has requested emergency support from their network. They're going through 
            a particularly difficult time and could really use immediate encouragement or assistance.
            
            Please reach out as soon as possible - a phone call, text, or visit could be exactly 
            what they need right now.
            
            Thank you for being there when it matters most. ❤️
            """
        }
        
        return templates.get(trigger_type, "Your friend could use some support with their goals right now!")
    
    @staticmethod
    def _send_support_email(contact, user, message, trigger_type, context_data):
        """Send email to support contact"""
        try:
            subject_map = {
                'mood_low': f"🤗 {user.get_full_name() or user.username} could use some encouragement",
                'adherence_drop': f"💪 Help {user.get_full_name() or user.username} get back on track",
                'missed_activities': f"📅 Check in on {user.get_full_name() or user.username}",
                'emergency': f"🚨 URGENT: {user.get_full_name() or user.username} needs support"
            }
            
            subject = subject_map.get(trigger_type, f"Support needed for {user.get_full_name() or user.username}")
            
            # Add user name to context data
            if context_data is None:
                context_data = {}
            context_data['user_name'] = user.get_full_name() or user.username
            
            # Update message with proper context
            message = SupportNetworkService._get_message_template(trigger_type, context_data)
            
            # Render email template
            html_message = render_to_string('emails/support_notification.html', {
                'contact_name': contact.name,
                'user_name': user.get_full_name() or user.username,
                'message': message,
                'trigger_type': trigger_type,
                'context_data': context_data,
                'user_relationship': contact.relationship
            })
            
            # Send email
            send_mail(
                subject=subject,
                message=message,  # Plain text fallback
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[contact.email],
                html_message=html_message,
                fail_silently=False
            )
            
            logger.info(f"Support email sent to {contact.email} for user {user.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending support email to {contact.email}: {str(e)}")
            return False
    
    @staticmethod
    def get_support_dashboard_data(contact_id):
        """Get dashboard data for support contact"""
        try:
            contact = SupportContact.objects.get(id=contact_id, is_active=True)
            user = contact.user
            
            # Get recent activity
            recent_logs = UserDailyLog.objects.filter(
                user=user,
                log_date__gte=timezone.now().date() - timedelta(days=30)
            ).order_by('-log_date')
            
            # Get current goals
            active_goals = user.monk_mode_goals.filter(current_status='active')
            
            # Calculate averages
            mood_avg = recent_logs.aggregate(
                avg_mood=models.Avg('mood_rating')
            )['avg_mood'] or 0
            
            adherence_avg = recent_logs.aggregate(
                avg_adherence=models.Avg('adherence_score')
            )['avg_adherence'] or 0
            
            # Get recent notifications sent to this contact
            recent_notifications = SupportNotification.objects.filter(
                support_contact=contact,
                sent_at__gte=timezone.now() - timedelta(days=30)
            ).order_by('-sent_at')
            
            return {
                'contact': contact,
                'user': user,
                'active_goals': active_goals,
                'recent_logs': recent_logs[:7],  # Last 7 days
                'mood_average': round(mood_avg, 1),
                'adherence_average': round(adherence_avg, 1),
                'recent_notifications': recent_notifications[:5],
                'total_goals': user.monk_mode_goals.count(),
                'completed_goals': user.monk_mode_goals.filter(current_status='completed').count()
            }
            
        except SupportContact.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting support dashboard data: {str(e)}")
            return None
    
    @staticmethod
    def request_emergency_support(user, message=""):
        """User requests emergency support from their network"""
        try:
            emergency_contacts = SupportContact.objects.filter(
                user=user,
                is_active=True,
                emergency_contact=True
            )
            
            if not emergency_contacts.exists():
                # Fall back to all contacts if no emergency contacts
                emergency_contacts = SupportContact.objects.filter(
                    user=user,
                    is_active=True
                )
            
            if not emergency_contacts.exists():
                return False
            
            context_data = {
                'user_message': message,
                'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M'),
                'user_name': user.get_full_name() or user.username
            }
            
            notifications_sent = 0
            for contact in emergency_contacts:
                notification = SupportNotification.objects.create(
                    user=user,
                    support_contact=contact,
                    trigger_type='emergency',
                    message_template=f"Emergency support requested: {message}",
                    sent_at=timezone.now()
                )
                
                success = SupportNetworkService._send_support_email(
                    contact, user, f"Emergency support requested: {message}", 
                    'emergency', context_data
                )
                
                if success:
                    notifications_sent += 1
                else:
                    notification.delete()
            
            return notifications_sent > 0
            
        except Exception as e:
            logger.error(f"Error requesting emergency support: {str(e)}")
            return False