import json
import requests
from django.conf import settings
from django.utils import timezone
from apps.core.models import (
    AIPromptHistory, MonkModeGoal, MonkModePeriod, ScheduledActivity, 
    ActivityType, UserDailyLog, SupportContact
)
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AIService:
    """
    Enhanced AI service with support for plan generation, task prioritization,
    and intelligent recommendations using Google Gemini API.
    """
    
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    
    @staticmethod
    def send_message_to_gemini(user_id, goal_id, message_text, chat_history=None, message_type='chat'):
        """Send message to Gemini API with enhanced context"""
        try:
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            goal = MonkModeGoal.objects.get(id=goal_id, user=user) if goal_id else None
            
            # Save user message to history
            user_prompt = AIPromptHistory.objects.create(
                user=user,
                monk_mode_goal=goal,
                role='user',
                message_text=message_text,
                message_type=message_type
            )
            
            # Build comprehensive context
            context = AIService._build_user_context(user, goal)
            
            # Get conversation history
            if chat_history is None:
                chat_history = AIPromptHistory.objects.filter(
                    user=user,
                    monk_mode_goal=goal
                ).order_by('timestamp')[-10:]  # Last 10 messages
            
            # Build system prompt
            system_prompt = AIService._build_system_prompt(context, message_type)
            
            # Build conversation for Gemini
            conversation = AIService._build_gemini_conversation(
                system_prompt, chat_history, message_text
            )
            
            # Call Gemini API
            response = AIService._call_gemini_api(conversation)
            
            if response and 'candidates' in response:
                ai_response = response['candidates'][0]['content']['parts'][0]['text']
                
                # Save AI response
                ai_prompt = AIPromptHistory.objects.create(
                    user=user,
                    monk_mode_goal=goal,
                    role='model',
                    message_text=ai_response,
                    message_type=message_type
                )
                
                # Check if response contains structured plan
                plan_generated = False
                monk_mode_period_id = None
                
                if AIService._contains_structured_plan(ai_response):
                    period = AIService._parse_and_create_plan(user, goal, ai_response)
                    if period:
                        plan_generated = True
                        monk_mode_period_id = period.id
                
                return {
                    'ai_response': ai_response,
                    'plan_generated': plan_generated,
                    'monk_mode_period_id': monk_mode_period_id,
                    'conversation_id': user_prompt.id,
                    'status': 'success'
                }
            else:
                logger.error(f"Invalid response from Gemini API: {response}")
                return {
                    'ai_response': "I'm experiencing technical difficulties. Please try again.",
                    'plan_generated': False,
                    'status': 'error'
                }
                
        except Exception as e:
            logger.error(f"Error in send_message_to_gemini: {str(e)}")
            return {
                'ai_response': "I'm sorry, I encountered an error. Please try again.",
                'plan_generated': False,
                'status': 'error'
            }
    
    @staticmethod
    def _build_user_context(user, goal=None):
        """Build comprehensive user context for AI"""
        context = {
            'user_name': user.get_full_name() or user.username,
            'current_date': timezone.now().strftime('%Y-%m-%d'),
            'current_time': timezone.now().strftime('%H:%M'),
        }
        
        if goal:
            context.update({
                'goal_title': goal.title,
                'goal_description': goal.description,
                'goal_start_date': goal.start_date.strftime('%Y-%m-%d'),
                'goal_end_date': goal.end_date.strftime('%Y-%m-%d'),
                'goal_status': goal.current_status,
                'completion_percentage': goal.completion_percentage
            })
            
            # Add objectives
            objectives = goal.objectives.all()
            context['objectives'] = [
                {
                    'description': obj.description,
                    'due_date': obj.due_date.strftime('%Y-%m-%d') if obj.due_date else None,
                    'is_completed': obj.is_completed,
                    'priority_score': obj.priority_score
                }
                for obj in objectives
            ]
        
        # Add recent activity data
        recent_logs = UserDailyLog.objects.filter(
            user=user,
            log_date__gte=timezone.now().date() - timedelta(days=7)
        ).order_by('-log_date')
        
        if recent_logs.exists():
            context['recent_performance'] = {
                'avg_mood': sum(log.mood_rating for log in recent_logs if log.mood_rating) / max(1, len([log for log in recent_logs if log.mood_rating])),
                'avg_adherence': sum(log.adherence_score for log in recent_logs if log.adherence_score) / max(1, len([log for log in recent_logs if log.adherence_score])),
                'recent_challenges': [log.challenges_faced for log in recent_logs[:3] if log.challenges_faced]
            }
        
        # Add support network info
        support_contacts = SupportContact.objects.filter(user=user, is_active=True)
        context['has_support_network'] = support_contacts.exists()
        context['support_network_size'] = support_contacts.count()
        
        return context
    
    @staticmethod
    def _build_system_prompt(context, message_type):
        """Build system prompt based on context and message type"""
        base_prompt = f"""
        You are an expert Monk Mode productivity coach helping {context['user_name']} achieve their goals through focused, structured periods of work and personal development.
        
        Current date: {context['current_date']}
        Current time: {context['current_time']}
        """
        
        if message_type == 'chat':
            return base_prompt + """
            Your role is to:
            1. Provide motivational support and guidance
            2. Ask clarifying questions to understand their needs
            3. Suggest improvements to their Monk Mode approach
            4. Help them overcome challenges and obstacles
            5. When ready, generate a structured Monk Mode plan
            
            Keep responses conversational, supportive, and actionable. If the user seems ready for a plan, ask key questions about their schedule, energy levels, and preferences before generating the structured JSON plan.
            """
        
        elif message_type == 'plan_generation':
            return base_prompt + """
            Your role is to generate a comprehensive, personalized Monk Mode schedule in JSON format.
            
            CRITICAL: When generating a plan, you MUST output valid JSON in this exact structure:
            {
              "monk_mode_plan_name": "Descriptive name for the plan",
              "period_start_date": "YYYY-MM-DD",
              "period_end_date": "YYYY-MM-DD",
              "daily_schedules": [
                {
                  "day_number": 1,
                  "date": "YYYY-MM-DD",
                  "activities": [
                    {
                      "activity_type": "Sleep",
                      "start_time": "00:00",
                      "end_time": "07:00",
                      "description": "Deep restorative sleep",
                      "energy_required": 1
                    },
                    {
                      "activity_type": "Deep Work",
                      "start_time": "09:00",
                      "end_time": "12:00",
                      "description": "Focused work on main objective",
                      "energy_required": 8
                    }
                  ]
                }
              ]
            }
            
            Include these activity types: Sleep, Deep Work, Exercise, Mindfulness, Cooking, Partner Time, Learning, Break, Reflection.
            Assign realistic energy_required values (1-10).
            """
        
        elif message_type == 'priority_request':
            return base_prompt + """
            Your role is to help prioritize tasks and activities based on:
            1. Goal impact and urgency
            2. Energy requirements and user's current energy
            3. Dependencies between tasks
            4. User's productivity patterns
            5. Time constraints
            
            Provide clear, actionable priority recommendations with reasoning.
            """
        
        return base_prompt
    
    @staticmethod
    def _build_gemini_conversation(system_prompt, chat_history, current_message):
        """Build conversation format for Gemini API"""
        conversation = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": system_prompt}]
                }
            ]
        }
        
        # Add chat history
        for message in chat_history:
            role = "user" if message.role == "user" else "model"
            conversation["contents"].append({
                "role": role,
                "parts": [{"text": message.message_text}]
            })
        
        # Add current message
        conversation["contents"].append({
            "role": "user",
            "parts": [{"text": current_message}]
        })
        
        return conversation
    
    @staticmethod
    def _call_gemini_api(conversation):
        """Make API call to Gemini"""
        try:
            headers = {
                'Content-Type': 'application/json',
            }
            
            url = f"{AIService.GEMINI_API_URL}?key={settings.GEMINI_API_KEY}"
            
            payload = {
                **conversation,
                "generationConfig": {
                    "temperature": 0.7,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                }
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Gemini API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error calling Gemini API: {str(e)}")
            return None
    
    @staticmethod
    def _contains_structured_plan(response_text):
        """Check if response contains structured JSON plan"""
        try:
            # Look for JSON structure indicators
            if '{' in response_text and '"monk_mode_plan_name"' in response_text:
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def _parse_and_create_plan(user, goal, ai_response):
        """Parse AI response and create MonkModePeriod with activities"""
        try:
            # Extract JSON from response
            json_start = ai_response.find('{')
            json_end = ai_response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON found in AI response")
                return None
            
            json_str = ai_response[json_start:json_end]
            plan_data = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['monk_mode_plan_name', 'period_start_date', 'period_end_date', 'daily_schedules']
            for field in required_fields:
                if field not in plan_data:
                    logger.error(f"Missing required field: {field}")
                    return None
            
            # Create MonkModePeriod
            period = MonkModePeriod.objects.create(
                goal=goal,
                period_name=plan_data['monk_mode_plan_name'],
                start_date=datetime.strptime(plan_data['period_start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(plan_data['period_end_date'], '%Y-%m-%d').date(),
                ai_generated_json=plan_data,
                is_active=True
            )
            
            # Create scheduled activities
            for daily_schedule in plan_data['daily_schedules']:
                day_number = daily_schedule['day_number']
                
                for activity_data in daily_schedule['activities']:
                    # Get or create activity type
                    activity_type, _ = ActivityType.objects.get_or_create(
                        name=activity_data['activity_type'],
                        defaults={
                            'description': f"Generated activity type: {activity_data['activity_type']}",
                            'energy_requirement': activity_data.get('energy_required', 5)
                        }
                    )
                    
                    # Calculate duration
                    start_time = datetime.strptime(activity_data['start_time'], '%H:%M').time()
                    end_time = datetime.strptime(activity_data['end_time'], '%H:%M').time()
                    
                    start_datetime = datetime.combine(datetime.today(), start_time)
                    end_datetime = datetime.combine(datetime.today(), end_time)
                    
                    # Handle overnight activities
                    if end_time < start_time:
                        end_datetime += timedelta(days=1)
                    
                    duration_minutes = int((end_datetime - start_datetime).total_seconds() / 60)
                    
                    # Create scheduled activity
                    ScheduledActivity.objects.create(
                        monk_mode_period=period,
                        activity_type=activity_type,
                        day_of_period=day_number,
                        start_time=start_time,
                        end_time=end_time,
                        duration_minutes=duration_minutes,
                        description=activity_data.get('description', ''),
                        energy_required=activity_data.get('energy_required', 5)
                    )
            
            logger.info(f"Successfully created MonkModePeriod {period.id} for user {user.id}")
            return period
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error parsing and creating plan: {str(e)}")
            return None
    
    @staticmethod
    def generate_priority_recommendations(user, activities_queryset=None):
        """Generate AI-powered priority recommendations"""
        try:
            if activities_queryset is None:
                # Get today's activities
                today = timezone.now().date()
                active_period = user.monk_mode_goals.filter(current_status='active').first()
                
                if not active_period or not active_period.periods.filter(is_active=True).exists():
                    return "No active Monk Mode period found."
                
                period = active_period.periods.filter(is_active=True).first()
                day_of_period = (today - period.start_date).days + 1
                
                activities_queryset = ScheduledActivity.objects.filter(
                    monk_mode_period=period,
                    day_of_period=day_of_period,
                    is_completed=False
                )
            
            if not activities_queryset.exists():
                return "No activities found for prioritization."
            
            # Build context for AI
            activities_context = []
            for activity in activities_queryset:
                activities_context.append({
                    'description': activity.description,
                    'activity_type': activity.activity_type.name,
                    'start_time': activity.start_time.strftime('%H:%M'),
                    'duration': activity.duration_minutes,
                    'energy_required': activity.energy_required,
                    'priority_score': getattr(activity, 'priority_score', 0)
                })
            
            # Prepare message for AI
            priority_message = f"""
            Please help me prioritize these activities for today. Consider:
            1. Goal impact and urgency
            2. Energy requirements vs. my current energy level
            3. Time constraints and dependencies
            4. Optimal sequencing for productivity
            
            Activities to prioritize:
            {json.dumps(activities_context, indent=2)}
            
            Please provide:
            1. Top 3 priority activities in order
            2. Reasoning for each priority
            3. Suggested focus strategy for the day
            4. Any schedule adjustments you recommend
            """
            
            # Get AI response
            response = AIService.send_message_to_gemini(
                user.id, None, priority_message, message_type='priority_request'
            )
            
            if response['status'] == 'success':
                return response['ai_response']
            else:
                return "Unable to generate priority recommendations at this time."
                
        except Exception as e:
            logger.error(f"Error generating priority recommendations: {str(e)}")
            return "Error generating priority recommendations."
    
    @staticmethod
    def generate_motivational_message(user, context_type='general'):
        """Generate personalized motivational message"""
        try:
            # Get user context
            context = AIService._build_user_context(user)
            
            # Build context-specific message
            if context_type == 'low_mood':
                base_message = """
                I've been tracking my mood and it's been low recently. I could use some encouragement 
                and motivation to keep going with my Monk Mode journey. Please provide personalized 
                motivation based on my goals and recent progress.
                """
            elif context_type == 'milestone':
                base_message = """
                I've reached a milestone in my Monk Mode journey! Please help me celebrate this 
                achievement and motivate me to continue toward my ultimate goal.
                """
            elif context_type == 'struggling':
                base_message = """
                I'm struggling to stick to my Monk Mode schedule and feeling discouraged. 
                Please provide guidance and motivation to help me get back on track.
                """
            else:
                base_message = """
                Please provide me with some personalized motivation and encouragement for my 
                Monk Mode journey based on my current goals and progress.
                """
            
            response = AIService.send_message_to_gemini(
                user.id, context.get('goal_id'), base_message, message_type='chat'
            )
            
            if response['status'] == 'success':
                return response['ai_response']
            else:
                return "Stay strong! Every step forward, no matter how small, brings you closer to your goals."
                
        except Exception as e:
            logger.error(f"Error generating motivational message: {str(e)}")
            return "Keep pushing forward! You've got this!"
    
    @staticmethod
    def analyze_progress_and_suggest_adjustments(user, goal):
        """Analyze user's progress and suggest plan adjustments"""
        try:
            # Get recent performance data
            recent_logs = UserDailyLog.objects.filter(
                user=user,
                log_date__gte=timezone.now().date() - timedelta(days=14)
            ).order_by('-log_date')
            
            # Get completed activities
            completed_activities = ScheduledActivity.objects.filter(
                monk_mode_period__goal=goal,
                is_completed=True,
                completed_at__gte=timezone.now() - timedelta(days=14)
            )
            
            # Build analysis context
            analysis_context = {
                'goal_completion_percentage': goal.completion_percentage,
                'recent_mood_avg': sum(log.mood_rating for log in recent_logs if log.mood_rating) / max(1, len([log for log in recent_logs if log.mood_rating])),
                'recent_adherence_avg': sum(log.adherence_score for log in recent_logs if log.adherence_score) / max(1, len([log for log in recent_logs if log.adherence_score])),
                'activities_completed': completed_activities.count(),
                'major_challenges': [log.challenges_faced for log in recent_logs[:5] if log.challenges_faced],
                'recent_wins': [log.wins_of_the_day for log in recent_logs[:5] if log.wins_of_the_day]
            }
            
            analysis_message = f"""
            Please analyze my Monk Mode progress and suggest adjustments to improve my success:
            
            Current Progress Analysis:
            - Goal completion: {analysis_context['goal_completion_percentage']:.1f}%
            - Average mood (last 14 days): {analysis_context['recent_mood_avg']:.1f}/5
            - Average adherence: {analysis_context['recent_adherence_avg']:.1f}/10
            - Activities completed: {analysis_context['activities_completed']}
            
            Recent challenges: {analysis_context['major_challenges'][:3]}
            Recent wins: {analysis_context['recent_wins'][:3]}
            
            Based on this data, please provide:
            1. Assessment of my current trajectory
            2. Specific areas that need adjustment
            3. Concrete suggestions for improving adherence
            4. Any schedule modifications you recommend
            5. Strategies to overcome recurring challenges
            """
            
            response = AIService.send_message_to_gemini(
                user.id, goal.id, analysis_message, message_type='chat'
            )
            
            if response['status'] == 'success':
                return response['ai_response']
            else:
                return "Unable to generate progress analysis at this time."
                
        except Exception as e:
            logger.error(f"Error analyzing progress: {str(e)}")
            return "Error analyzing progress."
    
    @staticmethod
    def generate_weekly_review_insights(user):
        """Generate AI insights for weekly review"""
        try:
            # Get past week's data
            week_start = timezone.now().date() - timedelta(days=7)
            
            weekly_logs = UserDailyLog.objects.filter(
                user=user,
                log_date__gte=week_start
            ).order_by('log_date')
            
            completed_activities = ScheduledActivity.objects.filter(
                monk_mode_period__goal__user=user,
                completed_at__gte=timezone.combine(week_start, datetime.min.time()),
                is_completed=True
            )
            
            # Calculate weekly metrics
            weekly_metrics = {
                'days_logged': weekly_logs.count(),
                'avg_mood': sum(log.mood_rating for log in weekly_logs if log.mood_rating) / max(1, len([log for log in weekly_logs if log.mood_rating])),
                'avg_adherence': sum(log.adherence_score for log in weekly_logs if log.adherence_score) / max(1, len([log for log in weekly_logs if log.adherence_score])),
                'activities_completed': completed_activities.count(),
                'total_deep_work_hours': sum(
                    activity.duration_minutes / 60 
                    for activity in completed_activities 
                    if 'deep work' in activity.activity_type.name.lower()
                ),
                'consistency_score': weekly_logs.count() / 7 * 100  # Percentage of days logged
            }
            
            review_message = f"""
            Please provide insights for my weekly Monk Mode review:
            
            This Week's Performance:
            - Days with logs: {weekly_metrics['days_logged']}/7
            - Average mood: {weekly_metrics['avg_mood']:.1f}/5
            - Average adherence: {weekly_metrics['avg_adherence']:.1f}/10
            - Activities completed: {weekly_metrics['activities_completed']}
            - Deep work hours: {weekly_metrics['total_deep_work_hours']:.1f}
            - Consistency score: {weekly_metrics['consistency_score']:.1f}%
            
            Key challenges this week:
            {[log.challenges_faced for log in weekly_logs if log.challenges_faced]}
            
            Wins this week:
            {[log.wins_of_the_day for log in weekly_logs if log.wins_of_the_day]}
            
            Please provide:
            1. Overall assessment of the week
            2. Key patterns you notice (positive and negative)
            3. Specific wins to celebrate
            4. Areas for improvement next week
            5. One concrete action item for better performance
            6. Motivational message for the upcoming week
            """
            
            response = AIService.send_message_to_gemini(
                user.id, None, review_message, message_type='chat'
            )
            
            if response['status'] == 'success':
                return response['ai_response']
            else:
                return "Great work this week! Keep building on your progress."
                
        except Exception as e:
            logger.error(f"Error generating weekly review insights: {str(e)}")
            return "Unable to generate weekly insights at this time."
    
    @staticmethod
    def suggest_goal_adjustments(user, goal):
        """Suggest adjustments to goal based on progress"""
        try:
            # Calculate time remaining
            days_total = (goal.end_date - goal.start_date).days
            days_elapsed = (timezone.now().date() - goal.start_date).days
            days_remaining = (goal.end_date - timezone.now().date()).days
            
            # Get completion rate
            completion_percentage = goal.completion_percentage
            expected_completion = (days_elapsed / days_total) * 100 if days_total > 0 else 0
            
            # Get recent performance
            recent_adherence = UserDailyLog.objects.filter(
                user=user,
                log_date__gte=timezone.now().date() - timedelta(days=7),
                adherence_score__isnull=False
            ).aggregate(avg=models.Avg('adherence_score'))['avg'] or 0
            
            adjustment_message = f"""
            Please analyze my goal progress and suggest adjustments:
            
            Goal Analysis:
            - Total duration: {days_total} days
            - Days elapsed: {days_elapsed}
            - Days remaining: {days_remaining}
            - Current completion: {completion_percentage:.1f}%
            - Expected completion at this point: {expected_completion:.1f}%
            - Progress gap: {completion_percentage - expected_completion:.1f}% 
            - Recent adherence: {recent_adherence:.1f}/10
            
            Goal: {goal.title}
            Description: {goal.description}
            Target outcome: {goal.target_outcome}
            
            Please suggest:
            1. Is my goal timeline realistic given current progress?
            2. Should I adjust the scope or timeline?
            3. What specific changes would improve my success rate?
            4. How can I accelerate progress if behind schedule?
            5. Any red flags or concerns about current trajectory?
            """
            
            response = AIService.send_message_to_gemini(
                user.id, goal.id, adjustment_message, message_type='chat'
            )
            
            if response['status'] == 'success':
                return response['ai_response']
            else:
                return "Consider reviewing your goal timeline and breaking down remaining tasks into smaller, manageable steps."
                
        except Exception as e:
            logger.error(f"Error suggesting goal adjustments: {str(e)}")
            return "Unable to generate goal adjustment suggestions."
    
    @staticmethod
    def generate_emergency_motivation(user, crisis_context=""):
        """Generate emergency motivational intervention"""
        try:
            emergency_message = f"""
            EMERGENCY MOTIVATION NEEDED: I'm having a really difficult time with my Monk Mode journey right now. 
            {crisis_context}
            
            I need immediate, powerful motivation to help me push through this challenging moment. 
            Please provide:
            1. Immediate encouragement and perspective
            2. Reminder of why I started this journey
            3. Small, actionable step I can take right now
            4. Affirmation of my capabilities
            5. Hope for getting through this difficult moment
            
            Please be extra supportive and understanding - I really need this right now.
            """
            
            response = AIService.send_message_to_gemini(
                user.id, None, emergency_message, message_type='chat'
            )
            
            if response['status'] == 'success':
                return response['ai_response']
            else:
                return """
                🤗 I believe in you! This difficult moment is temporary, but your strength is permanent.
                
                Take one deep breath. You've overcome challenges before, and you will overcome this one too.
                
                Right now, just focus on the next small step - not the whole journey, just the next step.
                
                You started this Monk Mode journey for important reasons. Those reasons are still valid, and you are still capable of achieving your goals.
                
                This struggle you're feeling? It's not failure - it's growth. Every person who has achieved something meaningful has felt exactly what you're feeling right now.
                
                You've got this. One moment at a time. 💪
                """
                
        except Exception as e:
            logger.error(f"Error generating emergency motivation: {str(e)}")
            return "You're stronger than you know. This difficult moment will pass. Keep going - one step at a time. 💙"