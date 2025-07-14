from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from apps.core.models import (
    MotivationMedia, SelfLetter, UserCommitment, UserDailyLog, MonkModeGoal
)
from datetime import datetime, timedelta
import random
import logging

logger = logging.getLogger(__name__)

class MotivationService:
    
    @staticmethod
    def get_daily_motivation(user, trigger_type='morning'):
        """Get motivation content for user based on trigger"""
        try:
            # Get motivation media for this trigger
            motivation_media = MotivationMedia.objects.filter(
                user=user,
                display_triggers__contains=[trigger_type]
            ).order_by('last_shown', '?')  # Prioritize least recently shown
            
            selected_media = []
            
            # Select up to 3 pieces of motivation content
            for media in motivation_media[:3]:
                # Update last_shown timestamp
                media.last_shown = timezone.now()
                media.save()
                selected_media.append(media)
            
            # Check for self letters ready for delivery
            ready_letters = SelfLetter.objects.filter(
                user=user,
                is_delivered=False,
                delivery_trigger=trigger_type
            )
            
            # Check scheduled letters
            scheduled_letters = SelfLetter.objects.filter(
                user=user,
                is_delivered=False,
                delivery_trigger='scheduled',
                delivery_date__lte=timezone.now()
            )
            
            letters_to_deliver = list(ready_letters) + list(scheduled_letters)
            
            return {
                'motivation_media': selected_media,
                'letters': letters_to_deliver,
                'timestamp': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"Error getting daily motivation for user {user.id}: {str(e)}")
            return {'motivation_media': [], 'letters': [], 'timestamp': timezone.now()}
    
    @staticmethod
    def trigger_mood_motivation(user):
        """Trigger motivation content when mood is low"""
        try:
            # Get mood-specific motivation
            mood_motivation = MotivationMedia.objects.filter(
                user=user,
                display_triggers__contains=['mood_low']
            ).order_by('?')[:2]  # Random selection
            
            # Get emergency self letters
            emergency_letters = SelfLetter.objects.filter(
                user=user,
                is_delivered=False,
                delivery_trigger='mood_low'
            )[:1]
            
            # Get user's commitment as reminder
            commitments = UserCommitment.objects.filter(
                user=user,
                is_active=True
            )
            
            motivation_package = {
                'motivation_media': list(mood_motivation),
                'letters': list(emergency_letters),
                'commitments': list(commitments),
                'motivational_quotes': MotivationService._get_emergency_quotes(),
                'trigger_reason': 'mood_support'
            }
            
            # Mark letters as delivered
            for letter in emergency_letters:
                letter.is_delivered = True
                letter.delivered_at = timezone.now()
                letter.save()
            
            # Update media last_shown
            for media in mood_motivation:
                media.last_shown = timezone.now()
                media.save()
            
            return motivation_package
            
        except Exception as e:
            logger.error(f"Error triggering mood motivation for user {user.id}: {str(e)}")
            return None
    
    @staticmethod
    def deliver_scheduled_letters(user=None):
        """Deliver scheduled self letters"""
        try:
            # Get letters ready for delivery
            query = SelfLetter.objects.filter(
                is_delivered=False,
                delivery_trigger='scheduled',
                delivery_date__lte=timezone.now()
            )
            
            if user:
                query = query.filter(user=user)
            
            letters_delivered = 0
            for letter in query:
                success = MotivationService._deliver_letter(letter)
                if success:
                    letters_delivered += 1
            
            return letters_delivered
            
        except Exception as e:
            logger.error(f"Error delivering scheduled letters: {str(e)}")
            return 0
    
    @staticmethod
    def _deliver_letter(letter):
        """Deliver individual self letter"""
        try:
            # Send email notification to user
            subject = f"📬 Letter from Past You: {letter.subject}"
            
            html_message = render_to_string('emails/self_letter.html', {
                'user_name': letter.user.get_full_name() or letter.user.username,
                'letter': letter,
                'delivery_date': timezone.now()
            })
            
            send_mail(
                subject=subject,
                message=letter.content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[letter.user.email],
                html_message=html_message,
                fail_silently=False
            )
            
            # Mark as delivered
            letter.is_delivered = True
            letter.delivered_at = timezone.now()
            letter.save()
            
            logger.info(f"Self letter delivered to user {letter.user.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error delivering letter {letter.id}: {str(e)}")
            return False
    
    @staticmethod
    def check_milestone_triggers(user, goal):
        """Check if milestone achievements should trigger motivation"""
        try:
            completion_percentage = goal.completion_percentage
            
            # Check for milestone letters
            milestone_triggers = []
            
            if completion_percentage >= 50 and completion_percentage < 60:
                milestone_triggers.append('halfway')
            
            if completion_percentage >= 100:
                milestone_triggers.append('completion')
            
            delivered_content = []
            
            for trigger in milestone_triggers:
                # Get milestone letters
                letters = SelfLetter.objects.filter(
                    user=user,
                    monk_mode_goal=goal,
                    delivery_trigger=trigger,
                    is_delivered=False
                )
                
                for letter in letters:
                    success = MotivationService._deliver_letter(letter)
                    if success:
                        delivered_content.append(letter)
                
                # Get milestone motivation media
                milestone_media = MotivationMedia.objects.filter(
                    user=user,
                    display_triggers__contains=['milestone']
                )
                
                for media in milestone_media:
                    media.last_shown = timezone.now()
                    media.save()
                    delivered_content.append(media)
            
            return delivered_content
            
        except Exception as e:
            logger.error(f"Error checking milestone triggers: {str(e)}")
            return []
    
    @staticmethod
    def create_commitment_contract(user, goal_id, commitment_data):
        """Create a formal commitment contract"""
        try:
            goal = MonkModeGoal.objects.get(id=goal_id, user=user)
            
            commitment = UserCommitment.objects.create(
                user=user,
                monk_mode_goal=goal,
                commitment_text=commitment_data['commitment_text'],
                consequences=commitment_data.get('consequences', ''),
                reward_for_success=commitment_data.get('reward_for_success', ''),
                public_commitment=commitment_data.get('public_commitment', False),
                witness_email=commitment_data.get('witness_email', '')
            )
            
            # Send commitment email to user
            MotivationService._send_commitment_email(commitment)
            
            # Send to witness if provided
            if commitment.witness_email:
                MotivationService._send_witness_email(commitment)
            
            return commitment
            
        except Exception as e:
            logger.error(f"Error creating commitment contract: {str(e)}")
            return None
    
    @staticmethod
    def _send_commitment_email(commitment):
        """Send commitment confirmation email"""
        try:
            subject = f"🤝 Your Commitment Contract: {commitment.monk_mode_goal.title}"
            
            html_message = render_to_string('emails/commitment_contract.html', {
                'user_name': commitment.user.get_full_name() or commitment.user.username,
                'commitment': commitment,
                'goal': commitment.monk_mode_goal
            })
            
            send_mail(
                subject=subject,
                message=commitment.commitment_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[commitment.user.email],
                html_message=html_message,
                fail_silently=False
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending commitment email: {str(e)}")
            return False
    
    @staticmethod
    def _send_witness_email(commitment):
        """Send email to commitment witness"""
        try:
            subject = f"🤝 Witness Request: {commitment.user.get_full_name() or commitment.user.username}'s Commitment"
            
            html_message = render_to_string('emails/commitment_witness.html', {
                'user_name': commitment.user.get_full_name() or commitment.user.username,
                'commitment': commitment,
                'goal': commitment.monk_mode_goal
            })
            
            send_mail(
                subject=subject,
                message=f"You've been asked to witness a commitment by {commitment.user.get_full_name() or commitment.user.username}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[commitment.witness_email],
                html_message=html_message,
                fail_silently=False
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending witness email: {str(e)}")
            return False
    
    @staticmethod
    def get_random_motivation_boost(user):
        """Get random motivation content for user"""
        try:
            # Random motivation media
            random_media = MotivationMedia.objects.filter(
                user=user,
                display_triggers__contains=['random']
            ).order_by('?')[:1]
            
            # Random motivational quote
            quotes = MotivationService._get_motivational_quotes()
            random_quote = random.choice(quotes) if quotes else None
            
            # User's active commitment as reminder
            commitment = UserCommitment.objects.filter(
                user=user,
                is_active=True
            ).first()
            
            return {
                'media': random_media.first() if random_media else None,
                'quote': random_quote,
                'commitment': commitment,
                'timestamp': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"Error getting random motivation boost: {str(e)}")
            return None
    
    @staticmethod
    def _get_motivational_quotes():
        """Get pool of motivational quotes"""
        return [
            "The only impossible journey is the one you never begin. - Tony Robbins",
            "Success is not final, failure is not fatal: it is the courage to continue that counts. - Winston Churchill",
            "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
            "It is during our darkest moments that we must focus to see the light. - Aristotle",
            "The only way to do great work is to love what you do. - Steve Jobs",
            "Don't watch the clock; do what it does. Keep going. - Sam Levenson",
            "The secret of getting ahead is getting started. - Mark Twain",
            "Your limitation—it's only your imagination.",
            "Sometimes later becomes never. Do it now.",
            "Great things never come from comfort zones.",
            "Dream it. Wish it. Do it.",
            "Success doesn't just find you. You have to go out and get it.",
            "The harder you work for something, the greater you'll feel when you achieve it.",
            "Don't stop when you're tired. Stop when you're done.",
            "Wake up with determination. Go to bed with satisfaction."
        ]
    
    @staticmethod
    def _get_emergency_quotes():
        """Get quotes specifically for difficult moments"""
        return [
            "This too shall pass. Every setback is a setup for a comeback.",
            "You are stronger than you think and more capable than you imagine.",
            "The mountain ahead may be tall, but you've already climbed so many others.",
            "One day at a time. One step at a time. You've got this.",
            "Remember why you started. That reason is still valid.",
            "Tough times don't last, but tough people do.",
            "You didn't come this far to only come this far.",
            "Every expert was once a beginner. Every pro was once an amateur.",
            "Progress, not perfection. Keep moving forward.",
            "The comeback is always stronger than the setback."
        ]
    
    @staticmethod
    def schedule_letter_delivery(user, letter_data):
        """Schedule a self letter for future delivery"""
        try:
            letter = SelfLetter.objects.create(
                user=user,
                subject=letter_data['subject'],
                content=letter_data['content'],
                delivery_date=letter_data.get('delivery_date'),
                delivery_trigger=letter_data['delivery_trigger'],
                monk_mode_goal_id=letter_data.get('goal_id')
            )
            
            return letter
            
        except Exception as e:
            logger.error(f"Error scheduling letter delivery: {str(e)}")
            return None
    
    @staticmethod
    def upload_motivation_media(user, media_data, file_obj=None):
        """Upload and process motivation media"""
        try:
            media = MotivationMedia.objects.create(
                user=user,
                media_type=media_data['media_type'],
                title=media_data['title'],
                description=media_data.get('description', ''),
                text_content=media_data.get('text_content', ''),
                display_triggers=media_data['display_triggers']
            )
            
            if file_obj and media_data['media_type'] != 'text':
                media.file_path = file_obj
                media.save()
            
            return media
            
        except Exception as e:
            logger.error(f"Error uploading motivation media: {str(e)}")
            return None