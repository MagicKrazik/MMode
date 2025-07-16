from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Count
from datetime import datetime, timedelta
import json
import logging

from apps.core.models import (
    MonkModeGoal, MonkModeObjective, MonkModePeriod, ScheduledActivity,
    UserDailyLog, AIPromptHistory, SupportContact, SupportNotification,
    MotivationMedia, SelfLetter, UserCommitment, TaskPriorityScore,
    EnergyLog, HabitStack, ActivityType
)

from apps.core.services.ai_service import AIService
from apps.core.services.support_service import SupportNetworkService
from apps.core.services.motivation_service import MotivationService
from apps.core.services.priority_engine import PriorityEngine
from apps.core.services.energy_service import EnergyManagementService

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """Main dashboard view with comprehensive overview and enhanced error handling"""
    user = request.user
    
    try:
        # Get active goals with optimized queries
        active_goals = MonkModeGoal.objects.filter(
            user=user, 
            current_status='active'
        ).prefetch_related('periods', 'objectives')
        
        # Get recent daily logs
        recent_logs = UserDailyLog.objects.filter(
            user=user
        ).order_by('-log_date')[:7]
        
        # Get today's activities if there's an active period
        today_activities = []
        current_period = None
        if active_goals.exists():
            active_goal = active_goals.first()
            active_periods = active_goal.periods.filter(is_active=True)
            if active_periods.exists():
                current_period = active_periods.first()
                today = timezone.now().date()
                day_of_period = (today - current_period.start_date).days + 1
                if day_of_period > 0:
                    today_activities = ScheduledActivity.objects.filter(
                        monk_mode_period=current_period,
                        day_of_period=day_of_period
                    ).select_related('activity_type').order_by('start_time')
        
        # Get daily motivation with error handling
        daily_motivation = None
        try:
            daily_motivation = MotivationService.get_daily_motivation(user, 'morning')
        except Exception as e:
            logger.warning(f"Error getting daily motivation for user {user.id}: {str(e)}")
            daily_motivation = {'message': 'Stay focused on your goals today!', 'type': 'text'}
        
        # Get focus recommendations with error handling
        focus_recommendations = []
        try:
            focus_recommendations = PriorityEngine.get_focus_recommendations(user)
        except Exception as e:
            logger.warning(f"Error getting focus recommendations for user {user.id}: {str(e)}")
            focus_recommendations = []
        
        # Get energy insights with error handling
        latest_energy = None
        energy_prediction = []
        try:
            latest_energy = EnergyLog.objects.filter(user=user).order_by('-timestamp').first()
            energy_prediction = EnergyManagementService.predict_energy_levels(user, hours_ahead=12)
        except Exception as e:
            logger.warning(f"Error getting energy data for user {user.id}: {str(e)}")
            latest_energy = None
            energy_prediction = []
        
        # Calculate dashboard metrics with error handling
        metrics = {
            'total_goals': MonkModeGoal.objects.filter(user=user).count(),
            'active_goals': active_goals.count(),
            'completed_goals': MonkModeGoal.objects.filter(user=user, current_status='completed').count(),
            'current_streak': _calculate_current_streak(user),
            'avg_mood_week': _calculate_avg_mood(user, 7),
            'avg_adherence_week': _calculate_avg_adherence(user, 7),
        }
        
        context = {
            'active_goals': active_goals,
            'recent_logs': recent_logs,
            'today_activities': today_activities,
            'current_period': current_period,
            'daily_motivation': daily_motivation,
            'focus_recommendations': focus_recommendations,
            'latest_energy': latest_energy,
            'energy_predictions': energy_prediction[:6] if energy_prediction else [],
            'metrics': metrics,
            'today': timezone.now().date(),
        }
        
    except Exception as e:
        logger.error(f"Dashboard error for user {user.id}: {str(e)}")
        messages.error(request, 'Error loading dashboard. Please try again.')
        context = {
            'active_goals': [],
            'recent_logs': [],
            'today_activities': [],
            'metrics': {'total_goals': 0, 'active_goals': 0, 'completed_goals': 0, 'current_streak': 0},
            'today': timezone.now().date(),
        }
    
    return render(request, 'dashboard/dashboard.html', context)

@login_required
def goals_list(request):
    """List all user goals with filtering and search"""
    try:
        goals = MonkModeGoal.objects.filter(user=request.user).select_related('user').order_by('-created_at')
        
        # Apply filters
        status_filter = request.GET.get('status')
        if status_filter:
            goals = goals.filter(current_status=status_filter)
        
        search_query = request.GET.get('search')
        if search_query:
            goals = goals.filter(
                Q(title__icontains=search_query) | 
                Q(description__icontains=search_query)
            )
        
        # Pagination
        paginator = Paginator(goals, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'status_filter': status_filter,
            'search_query': search_query,
        }
        
    except Exception as e:
        logger.error(f"Error in goals_list for user {request.user.id}: {str(e)}")
        messages.error(request, 'Error loading goals. Please try again.')
        context = {
            'page_obj': None,
            'status_filter': None,
            'search_query': None,
        }
    
    return render(request, 'dashboard/goals_list.html', context)

@login_required
def goal_detail(request, goal_id):
    """Detailed view of a specific goal with objective management"""
    goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    
    # Handle POST requests for adding objectives
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_objective':
            try:
                # Validate required fields
                description = request.POST.get('description', '').strip()
                if not description:
                    messages.error(request, 'Objective description is required.')
                    return redirect('dashboard:goal_detail', goal_id=goal.id)
                
                due_date = request.POST.get('due_date')
                if due_date:
                    due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                else:
                    due_date = None
                
                estimated_hours = request.POST.get('estimated_hours')
                if estimated_hours:
                    estimated_hours = int(estimated_hours)
                else:
                    estimated_hours = None
                
                difficulty_level = int(request.POST.get('difficulty_level', 3))
                
                objective = MonkModeObjective.objects.create(
                    goal=goal,
                    description=description,
                    due_date=due_date,
                    estimated_hours=estimated_hours,
                    difficulty_level=difficulty_level
                )
                messages.success(request, f'Objective "{objective.description}" added successfully!')
                
            except ValueError as e:
                messages.error(request, 'Please enter valid values for all fields.')
            except Exception as e:
                logger.error(f'Error adding objective for goal {goal_id}: {str(e)}')
                messages.error(request, f'Error adding objective: {str(e)}')
        
        elif action == 'complete_objective':
            try:
                objective_id = request.POST.get('objective_id')
                if not objective_id:
                    messages.error(request, 'Invalid objective ID.')
                    return redirect('dashboard:goal_detail', goal_id=goal.id)
                
                objective = get_object_or_404(MonkModeObjective, id=objective_id, goal=goal)
                objective.mark_completed()
                messages.success(request, 'Objective marked as completed!')
                
            except Exception as e:
                logger.error(f'Error completing objective: {str(e)}')
                messages.error(request, f'Error completing objective: {str(e)}')
        
        return redirect('dashboard:goal_detail', goal_id=goal.id)
    
    try:
        # Get objectives with prefetch
        objectives = goal.objectives.all().order_by('due_date', '-created_at')
        
        # Get periods with prefetch
        periods = goal.periods.all().order_by('-created_at')
        active_period = periods.filter(is_active=True).first()
        
        # Get recent activities if there's an active period
        recent_activities = []
        if active_period:
            recent_activities = ScheduledActivity.objects.filter(
                monk_mode_period=active_period
            ).select_related('activity_type').order_by('-day_of_period', 'start_time')[:20]
        
        # Get progress data
        progress_data = _calculate_goal_progress(goal)
        
        context = {
            'goal': goal,
            'objectives': objectives,
            'periods': periods,
            'active_period': active_period,
            'recent_activities': recent_activities,
            'progress_data': progress_data,
            'today': timezone.now().date(),
        }
        
    except Exception as e:
        logger.error(f"Error in goal_detail for goal {goal_id}: {str(e)}")
        messages.error(request, 'Error loading goal details.')
        context = {
            'goal': goal,
            'objectives': [],
            'periods': [],
            'active_period': None,
            'recent_activities': [],
            'progress_data': {'total_objectives': 0, 'completed_objectives': 0, 'total_activities': 0, 'completed_activities': 0},
            'today': timezone.now().date(),
        }
    
    return render(request, 'dashboard/goal_detail.html', context)

@login_required
def create_goal(request):
    """Create a new Monk Mode goal"""
    if request.method == 'POST':
        try:
            # Validate required fields
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            target_outcome = request.POST.get('target_outcome', '').strip()
            
            if not all([title, description, start_date, end_date, target_outcome]):
                messages.error(request, 'All required fields must be filled.')
                return render(request, 'dashboard/create_goal.html')
            
            # Validate dates
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            if end_date <= start_date:
                messages.error(request, 'End date must be after start date.')
                return render(request, 'dashboard/create_goal.html')
            
            # Validate optional numeric fields
            priority_level = int(request.POST.get('priority_level', 3))
            priority_level = max(1, min(5, priority_level))
            
            estimated_effort_hours = request.POST.get('estimated_effort_hours')
            if estimated_effort_hours:
                estimated_effort_hours = int(estimated_effort_hours)
            else:
                estimated_effort_hours = None
            
            goal = MonkModeGoal.objects.create(
                user=request.user,
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                target_outcome=target_outcome,
                priority_level=priority_level,
                estimated_effort_hours=estimated_effort_hours,
                support_network_enabled=request.POST.get('support_network_enabled') == 'on',
                motivation_reminders_enabled=request.POST.get('motivation_reminders_enabled') == 'on'
            )
            
            messages.success(request, f'Goal "{goal.title}" created successfully!')
            return redirect('dashboard:goal_detail', goal_id=goal.id)
            
        except ValueError as e:
            messages.error(request, 'Please enter valid values for all fields.')
        except Exception as e:
            logger.error(f'Error creating goal for user {request.user.id}: {str(e)}')
            messages.error(request, f'Error creating goal: {str(e)}')
    
    return render(request, 'dashboard/create_goal.html')

@login_required
def ai_chat(request, goal_id=None):
    """AI chat interface for goal planning and assistance"""
    goal = None
    if goal_id:
        goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    
    try:
        # Get recent chat history - FIXED: No negative indexing
        chat_history_qs = AIPromptHistory.objects.filter(
            user=request.user,
            monk_mode_goal=goal
        ).order_by('-timestamp')[:20]  # Get last 20 messages
        
        # Convert to list and reverse for chronological order
        chat_history = list(chat_history_qs)
        chat_history.reverse()
        
        if request.method == 'POST':
            message = request.POST.get('message', '').strip()
            if message:
                try:
                    response = AIService.send_message_to_gemini(
                        request.user.id,
                        goal.id if goal else None,
                        message
                    )
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(response)
                    else:
                        if response.get('plan_generated'):
                            messages.success(request, 'AI has generated a new Monk Mode plan for you!')
                            return redirect('dashboard:schedule_view', period_id=response['monk_mode_period_id'])
                        
                except Exception as e:
                    logger.error(f'Error in AI chat for user {request.user.id}: {str(e)}')
                    error_msg = 'Sorry, there was an error processing your message.'
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'ai_response': error_msg, 'status': 'error'})
                    else:
                        messages.error(request, error_msg)
        
        context = {
            'goal': goal,
            'chat_history': chat_history,
        }
        
    except Exception as e:
        logger.error(f"Error in ai_chat for user {request.user.id}: {str(e)}")
        messages.error(request, 'Error loading AI chat.')
        context = {
            'goal': goal,
            'chat_history': [],
        }
    
    return render(request, 'dashboard/ai_chat.html', context)

@login_required
def schedule_view(request, period_id):
    """View and manage schedule for a specific period"""
    period = get_object_or_404(MonkModePeriod, id=period_id, goal__user=request.user)
    
    try:
        # Get activities grouped by day with optimized query
        activities = ScheduledActivity.objects.filter(
            monk_mode_period=period
        ).select_related('activity_type').order_by('day_of_period', 'start_time')
        
        # Group activities by day
        activities_by_day = {}
        for activity in activities:
            day = activity.day_of_period
            if day not in activities_by_day:
                activities_by_day[day] = []
            activities_by_day[day].append(activity)
        
        # Get today's day number
        today = timezone.now().date()
        current_day = (today - period.start_date).days + 1 if today >= period.start_date else None
        
        context = {
            'period': period,
            'activities_by_day': activities_by_day,
            'current_day': current_day,
            'total_days': (period.end_date - period.start_date).days + 1,
        }
        
    except Exception as e:
        logger.error(f"Error in schedule_view for period {period_id}: {str(e)}")
        messages.error(request, 'Error loading schedule.')
        context = {
            'period': period,
            'activities_by_day': {},
            'current_day': None,
            'total_days': 0,
        }
    
    return render(request, 'dashboard/schedule_view.html', context)

@login_required
@require_POST
def complete_activity(request, activity_id):
    """Mark an activity as completed"""
    activity = get_object_or_404(ScheduledActivity, id=activity_id, monk_mode_period__goal__user=request.user)
    
    try:
        activity.is_completed = True
        activity.completed_at = timezone.now()
        
        # Get additional data from request with validation
        quality_rating = request.POST.get('quality_rating')
        if quality_rating:
            try:
                activity.completion_quality = max(1, min(5, int(quality_rating)))
            except ValueError:
                pass
        
        actual_start = request.POST.get('actual_start_time')
        actual_end = request.POST.get('actual_end_time')
        
        if actual_start:
            try:
                hour, minute = actual_start.split(':')
                activity.actual_start_time = timezone.now().replace(
                    hour=int(hour),
                    minute=int(minute),
                    second=0,
                    microsecond=0
                )
            except (ValueError, IndexError):
                pass
        
        if actual_end:
            try:
                hour, minute = actual_end.split(':')
                activity.actual_end_time = timezone.now().replace(
                    hour=int(hour),
                    minute=int(minute),
                    second=0,
                    microsecond=0
                )
            except (ValueError, IndexError):
                pass
        
        activity.save()
        
        # Update productivity patterns
        try:
            PriorityEngine.update_productivity_patterns(request.user)
        except Exception as e:
            logger.warning(f"Error updating productivity patterns: {str(e)}")
        
        # Check for milestone triggers
        try:
            MotivationService.check_milestone_triggers(request.user, activity.monk_mode_period.goal)
        except Exception as e:
            logger.warning(f"Error checking milestone triggers: {str(e)}")
        
        messages.success(request, f'Activity "{activity.description}" marked as completed!')
        
    except Exception as e:
        logger.error(f'Error completing activity {activity_id}: {str(e)}')
        messages.error(request, f'Error completing activity: {str(e)}')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect('dashboard:schedule_view', period_id=activity.monk_mode_period.id)

@login_required
def daily_log(request, date=None):
    """Daily logging interface with proper form handling"""
    if date:
        try:
            log_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            log_date = timezone.now().date()
    else:
        log_date = timezone.now().date()
    
    # Get or create daily log
    try:
        daily_log, created = UserDailyLog.objects.get_or_create(
            user=request.user,
            log_date=log_date,
            defaults={}
        )
    except Exception as e:
        logger.error(f"Error getting/creating daily log: {str(e)}")
        messages.error(request, 'Error accessing daily log.')
        return redirect('dashboard:dashboard')
    
    if request.method == 'POST':
        try:
            # Update daily log fields with proper validation
            daily_log.reflection_text = request.POST.get('reflection_text', '')
            
            # Handle numeric fields with validation
            def safe_int_convert(value, min_val, max_val, default=None):
                if not value or not value.strip():
                    return default
                try:
                    return max(min_val, min(max_val, int(value)))
                except ValueError:
                    return default
            
            daily_log.adherence_score = safe_int_convert(request.POST.get('adherence_score'), 1, 10)
            daily_log.mood_rating = safe_int_convert(request.POST.get('mood_rating'), 1, 5)
            daily_log.energy_level_morning = safe_int_convert(request.POST.get('energy_morning'), 1, 10)
            daily_log.energy_level_afternoon = safe_int_convert(request.POST.get('energy_afternoon'), 1, 10)
            daily_log.energy_level_evening = safe_int_convert(request.POST.get('energy_evening'), 1, 10)
            daily_log.sleep_quality = safe_int_convert(request.POST.get('sleep_quality'), 1, 5)
            daily_log.stress_level = safe_int_convert(request.POST.get('stress_level'), 1, 5)
            daily_log.environment_rating = safe_int_convert(request.POST.get('environment_rating'), 1, 5)
            daily_log.distractions_count = safe_int_convert(request.POST.get('distractions_count'), 0, 100, 0)
            
            daily_log.wins_of_the_day = request.POST.get('wins_of_the_day', '')
            daily_log.challenges_faced = request.POST.get('challenges_faced', '')
            
            daily_log.save()
            
            # Log current energy if provided
            current_energy = request.POST.get('current_energy')
            if current_energy and current_energy.strip():
                try:
                    EnergyManagementService.log_energy_level(
                        request.user,
                        int(current_energy),
                        context_factors={
                            'sleep_quality': daily_log.sleep_quality,
                            'stress_level': daily_log.stress_level,
                            'distractions': daily_log.distractions_count
                        },
                        notes=request.POST.get('energy_notes', '')
                    )
                except Exception as e:
                    logger.warning(f"Error logging energy level: {str(e)}")
            
            # Check for support triggers
            if daily_log.mood_rating and daily_log.mood_rating <= 2:
                try:
                    SupportNetworkService.check_mood_triggers(request.user)
                except Exception as e:
                    logger.warning(f"Error checking mood triggers: {str(e)}")
            
            if daily_log.adherence_score and daily_log.adherence_score <= 5:
                try:
                    SupportNetworkService.check_adherence_triggers(request.user)
                except Exception as e:
                    logger.warning(f"Error checking adherence triggers: {str(e)}")
            
            messages.success(request, 'Daily log updated successfully!')
            
        except Exception as e:
            logger.error(f'Error updating daily log: {str(e)}')
            messages.error(request, f'Error updating daily log: {str(e)}')
    
    # Get today's activities for reference
    today_activities = []
    try:
        active_goal = MonkModeGoal.objects.filter(user=request.user, current_status='active').first()
        if active_goal:
            active_period = active_goal.periods.filter(is_active=True).first()
            if active_period:
                day_of_period = (log_date - active_period.start_date).days + 1
                if day_of_period > 0:
                    today_activities = ScheduledActivity.objects.filter(
                        monk_mode_period=active_period,
                        day_of_period=day_of_period
                    ).select_related('activity_type').order_by('start_time')
    except Exception as e:
        logger.warning(f"Error getting today's activities: {str(e)}")
        today_activities = []
    
    context = {
        'daily_log': daily_log,
        'log_date': log_date,
        'today_activities': today_activities,
        'is_today': log_date == timezone.now().date(),
    }
    
    return render(request, 'dashboard/daily_log.html', context)

@login_required
def support_network(request):
    """Manage support network contacts"""
    try:
        contacts = SupportContact.objects.filter(user=request.user, is_active=True).order_by('name')
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'add_contact':
                try:
                    # Validate required fields
                    name = request.POST.get('name', '').strip()
                    email = request.POST.get('email', '').strip()
                    relationship = request.POST.get('relationship', '').strip()
                    
                    if not all([name, email, relationship]):
                        messages.error(request, 'Name, email, and relationship are required.')
                        return redirect('dashboard:support_network')
                    
                    SupportContact.objects.create(
                        user=request.user,
                        name=name,
                        email=email,
                        phone=request.POST.get('phone', ''),
                        relationship=relationship,
                        emergency_contact=request.POST.get('emergency_contact') == 'on',
                        notification_preferences=json.loads(request.POST.get('preferences', '{}'))
                    )
                    messages.success(request, 'Support contact added successfully!')
                    
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid preferences format.')
                except Exception as e:
                    logger.error(f'Error adding support contact: {str(e)}')
                    messages.error(request, f'Error adding contact: {str(e)}')
            
            elif action == 'request_support':
                try:
                    message = request.POST.get('support_message', '')
                    success = SupportNetworkService.request_emergency_support(request.user, message)
                    if success:
                        messages.success(request, 'Support request sent to your network!')
                    else:
                        messages.warning(request, 'No active support contacts found.')
                        
                except Exception as e:
                    logger.error(f'Error sending support request: {str(e)}')
                    messages.error(request, f'Error sending support request: {str(e)}')
        
        # Get recent notifications
        recent_notifications = SupportNotification.objects.filter(
            user=request.user
        ).order_by('-sent_at')[:10]
        
        context = {
            'contacts': contacts,
            'recent_notifications': recent_notifications,
        }
        
    except Exception as e:
        logger.error(f"Error in support_network for user {request.user.id}: {str(e)}")
        messages.error(request, 'Error loading support network.')
        context = {
            'contacts': [],
            'recent_notifications': [],
        }
    
    return render(request, 'dashboard/support_network.html', context)

@login_required  
def motivation_center(request):
    """Motivation and commitment management center"""
    user = request.user
    
    try:
        # Get user's motivation content
        motivation_media = MotivationMedia.objects.filter(user=user).order_by('-created_at')
        self_letters = SelfLetter.objects.filter(user=user).order_by('-created_at')
        commitments = UserCommitment.objects.filter(user=user, is_active=True)
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'upload_media':
                try:
                    # Validate required fields
                    media_type = request.POST.get('media_type', '').strip()
                    title = request.POST.get('title', '').strip()
                    
                    if not all([media_type, title]):
                        messages.error(request, 'Media type and title are required.')
                        return redirect('dashboard:motivation_center')
                    
                    media_data = {
                        'media_type': media_type,
                        'title': title,
                        'description': request.POST.get('description', ''),
                        'text_content': request.POST.get('text_content', ''),
                        'display_triggers': request.POST.getlist('display_triggers')
                    }
                    
                    file_obj = request.FILES.get('media_file')
                    media = MotivationService.upload_motivation_media(user, media_data, file_obj)
                    
                    if media:
                        messages.success(request, 'Motivation content uploaded successfully!')
                    else:
                        messages.error(request, 'Error uploading motivation content.')
                        
                except Exception as e:
                    logger.error(f'Error uploading motivation media: {str(e)}')
                    messages.error(request, f'Error uploading media: {str(e)}')
            
            elif action == 'schedule_letter':
                try:
                    # Validate required fields
                    subject = request.POST.get('subject', '').strip()
                    content = request.POST.get('content', '').strip()
                    delivery_trigger = request.POST.get('delivery_trigger', '').strip()
                    
                    if not all([subject, content, delivery_trigger]):
                        messages.error(request, 'Subject, content, and delivery trigger are required.')
                        return redirect('dashboard:motivation_center')
                    
                    letter_data = {
                        'subject': subject,
                        'content': content,
                        'delivery_trigger': delivery_trigger,
                        'goal_id': request.POST.get('goal_id'),
                    }
                    
                    if delivery_trigger == 'scheduled':
                        delivery_date = request.POST.get('delivery_date')
                        if delivery_date:
                            letter_data['delivery_date'] = datetime.strptime(
                                delivery_date, '%Y-%m-%d %H:%M'
                            )
                        else:
                            messages.error(request, 'Delivery date is required for scheduled letters.')
                            return redirect('dashboard:motivation_center')
                    
                    letter = MotivationService.schedule_letter_delivery(user, letter_data)
                    if letter:
                        messages.success(request, 'Letter scheduled successfully!')
                    else:
                        messages.error(request, 'Error scheduling letter.')
                        
                except ValueError as e:
                    messages.error(request, 'Invalid date format. Please use YYYY-MM-DD HH:MM.')
                except Exception as e:
                    logger.error(f'Error scheduling letter: {str(e)}')
                    messages.error(request, f'Error scheduling letter: {str(e)}')
            
            elif action == 'create_commitment':
                try:
                    active_goal = MonkModeGoal.objects.filter(user=user, current_status='active').first()
                    if active_goal:
                        commitment_text = request.POST.get('commitment_text', '').strip()
                        if not commitment_text:
                            messages.error(request, 'Commitment text is required.')
                            return redirect('dashboard:motivation_center')
                        
                        commitment_data = {
                            'commitment_text': commitment_text,
                            'consequences': request.POST.get('consequences', ''),
                            'reward_for_success': request.POST.get('reward_for_success', ''),
                            'public_commitment': request.POST.get('public_commitment') == 'on',
                            'witness_email': request.POST.get('witness_email', '')
                        }
                        
                        commitment = MotivationService.create_commitment_contract(
                            user, active_goal.id, commitment_data
                        )
                        
                        if commitment:
                            messages.success(request, 'Commitment contract created!')
                        else:
                            messages.error(request, 'Error creating commitment.')
                    else:
                        messages.warning(request, 'Please create an active goal first.')
                        
                except Exception as e:
                    logger.error(f'Error creating commitment: {str(e)}')
                    messages.error(request, f'Error creating commitment: {str(e)}')
        
        # Get daily motivation
        try:
            daily_motivation = MotivationService.get_daily_motivation(user)
        except Exception as e:
            logger.warning(f"Error getting daily motivation: {str(e)}")
            daily_motivation = None
        
        # Get user's active goals for letter scheduling
        active_goals = MonkModeGoal.objects.filter(user=user, current_status='active')
        
        context = {
            'motivation_media': motivation_media[:10],
            'self_letters': self_letters[:10],
            'commitments': commitments,
            'daily_motivation': daily_motivation,
            'active_goals': active_goals,
        }
        
    except Exception as e:
        logger.error(f"Error in motivation_center for user {user.id}: {str(e)}")
        messages.error(request, 'Error loading motivation center.')
        context = {
            'motivation_media': [],
            'self_letters': [],
            'commitments': [],
            'daily_motivation': None,
            'active_goals': [],
        }
    
    return render(request, 'dashboard/motivation_center.html', context)

@login_required
def priority_focus(request):
    """Task prioritization and focus recommendations"""
    user = request.user
    
    try:
        # Get today's focus recommendations
        focus_recommendations = PriorityEngine.get_focus_recommendations(user)
        
        # Get prioritized activities for today
        today = timezone.now().date()
        prioritized_activities = PriorityEngine.calculate_daily_priorities(user, today)
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'recalculate_priorities':
                try:
                    prioritized_activities = PriorityEngine.calculate_daily_priorities(user, today)
                    messages.success(request, 'Priorities recalculated successfully!')
                    
                except Exception as e:
                    logger.error(f'Error recalculating priorities: {str(e)}')
                    messages.error(request, f'Error recalculating priorities: {str(e)}')
            
            elif action == 'get_ai_recommendations':
                try:
                    ai_recommendations = AIService.generate_priority_recommendations(user)
                    messages.info(request, 'AI recommendations generated!')
                    
                    context = {
                        'focus_recommendations': focus_recommendations,
                        'prioritized_activities': prioritized_activities,
                        'ai_recommendations': ai_recommendations,
                    }
                    return render(request, 'dashboard/priority_focus.html', context)
                    
                except Exception as e:
                    logger.error(f'Error getting AI recommendations: {str(e)}')
                    messages.error(request, f'Error getting AI recommendations: {str(e)}')
        
        context = {
            'focus_recommendations': focus_recommendations,
            'prioritized_activities': prioritized_activities,
        }
        
    except Exception as e:
        logger.error(f"Error in priority_focus for user {user.id}: {str(e)}")
        messages.error(request, 'Error loading priority focus.')
        context = {
            'focus_recommendations': [],
            'prioritized_activities': [],
        }
    
    return render(request, 'dashboard/priority_focus.html', context)

@login_required
def energy_tracking(request):
    """Energy level tracking and insights"""
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'log_energy':
            try:
                energy_level = request.POST.get('energy_level')
                if not energy_level:
                    messages.error(request, 'Energy level is required.')
                    return redirect('dashboard:energy_tracking')
                
                energy_level = int(energy_level)
                if not (1 <= energy_level <= 10):
                    messages.error(request, 'Energy level must be between 1 and 10.')
                    return redirect('dashboard:energy_tracking')
                
                context_factors = {
                    'activity_before': request.POST.get('activity_before', ''),
                    'location': request.POST.get('location', ''),
                    'mood': request.POST.get('mood', ''),
                    'stress_level': request.POST.get('stress_level', ''),
                }
                notes = request.POST.get('notes', '')
                
                energy_log = EnergyManagementService.log_energy_level(
                    user, energy_level, context_factors, notes
                )
                
                if energy_log:
                    messages.success(request, 'Energy level logged successfully!')
                else:
                    messages.error(request, 'Error logging energy level.')
                    
            except (ValueError, KeyError) as e:
                messages.error(request, 'Please enter a valid energy level (1-10).')
            except Exception as e:
                logger.error(f'Error logging energy for user {user.id}: {str(e)}')
                messages.error(request, f'Error logging energy: {str(e)}')
    
    try:
        # Get energy insights
        energy_insights = EnergyManagementService.get_energy_insights(user)
        
        # Get recent energy logs
        recent_logs = EnergyLog.objects.filter(user=user).order_by('-timestamp')[:20]
        
        # Get energy predictions
        predictions = EnergyManagementService.predict_energy_levels(user, hours_ahead=24)
        
        # Get recovery recommendations
        recovery_recommendations = EnergyManagementService.get_recovery_recommendations(user)
        
        context = {
            'energy_insights': energy_insights,
            'recent_logs': recent_logs,
            'predictions': predictions[:12] if predictions else [],  # Next 12 hours
            'recovery_recommendations': recovery_recommendations,
        }
        
    except Exception as e:
        logger.error(f"Error in energy_tracking for user {user.id}: {str(e)}")
        messages.error(request, 'Error loading energy tracking data.')
        context = {
            'energy_insights': {},
            'recent_logs': [],
            'predictions': [],
            'recovery_recommendations': [],
        }
    
    return render(request, 'dashboard/energy_tracking.html', context)

@login_required
def progress_analytics(request):
    """Comprehensive progress analytics and insights"""
    user = request.user
    
    try:
        # Time period filter with validation
        try:
            days_back = int(request.GET.get('days', 30))
            days_back = max(7, min(365, days_back))  # Clamp between 7 and 365 days
        except (ValueError, TypeError):
            days_back = 30
        
        # Get goals data
        goals = MonkModeGoal.objects.filter(user=user)
        active_goals = goals.filter(current_status='active')
        completed_goals = goals.filter(current_status='completed')
        
        # Get daily logs for the period
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days_back)
        
        daily_logs = UserDailyLog.objects.filter(
            user=user,
            log_date__gte=start_date
        ).order_by('log_date')
        
        # Calculate analytics with error handling
        total_goals = goals.count()
        completed_count = completed_goals.count()
        
        analytics = {
            'total_goals': total_goals,
            'active_goals': active_goals.count(),
            'completed_goals': completed_count,
            'goal_completion_rate': (completed_count / max(1, total_goals)) * 100,
            'avg_mood': daily_logs.aggregate(avg=Avg('mood_rating'))['avg'] or 0,
            'avg_adherence': daily_logs.aggregate(avg=Avg('adherence_score'))['avg'] or 0,
            'avg_energy': daily_logs.aggregate(avg=Avg('energy_level_morning'))['avg'] or 0,
            'total_activities_completed': ScheduledActivity.objects.filter(
                monk_mode_period__goal__user=user,
                is_completed=True,
                completed_at__gte=timezone.datetime.combine(start_date, timezone.datetime.min.time())
            ).count(),
            'streak': _calculate_current_streak(user),
        }
        
        # Get weekly AI insights
        try:
            weekly_insights = AIService.generate_weekly_review_insights(user)
        except Exception as e:
            logger.warning(f"Error generating weekly insights: {str(e)}")
            weekly_insights = "Weekly insights temporarily unavailable."
        
        context = {
            'analytics': analytics,
            'daily_logs': daily_logs,
            'active_goals': active_goals,
            'completed_goals': completed_goals,
            'weekly_insights': weekly_insights,
            'days_back': days_back,
        }
        
    except Exception as e:
        logger.error(f"Error in progress_analytics for user {user.id}: {str(e)}")
        messages.error(request, 'Error loading analytics.')
        context = {
            'analytics': {
                'total_goals': 0, 'active_goals': 0, 'completed_goals': 0,
                'goal_completion_rate': 0, 'avg_mood': 0, 'avg_adherence': 0,
                'avg_energy': 0, 'total_activities_completed': 0, 'streak': 0
            },
            'daily_logs': [],
            'active_goals': [],
            'completed_goals': [],
            'weekly_insights': '',
            'days_back': 30,
        }
    
    return render(request, 'dashboard/progress_analytics.html', context)

@login_required
@require_POST
def emergency_support(request):
    """Emergency support request"""
    try:
        message = request.POST.get('message', 'Emergency support needed')
        success = SupportNetworkService.request_emergency_support(request.user, message)
        
        if success:
            # Also trigger emergency motivation
            try:
                emergency_motivation = MotivationService.trigger_mood_motivation(request.user)
            except Exception as e:
                logger.warning(f"Error triggering emergency motivation: {str(e)}")
                emergency_motivation = None
            
            return JsonResponse({
                'success': True,
                'message': 'Emergency support has been requested. Your support network has been notified.',
                'motivation': emergency_motivation
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No active support contacts found. Please add support contacts first.'
            })
            
    except Exception as e:
        logger.error(f'Error requesting emergency support for user {request.user.id}: {str(e)}')
        return JsonResponse({
            'success': False,
            'message': f'Error requesting support: {str(e)}'
        })

@login_required
def api_energy_log(request):
    """API endpoint for logging energy levels"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            energy_level = data.get('energy_level')
            
            if energy_level is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Energy level is required'
                }, status=400)
            
            energy_level = int(energy_level)
            if not (1 <= energy_level <= 10):
                return JsonResponse({
                    'success': False,
                    'error': 'Energy level must be between 1 and 10'
                }, status=400)
            
            context_factors = data.get('context_factors', {})
            notes = data.get('notes', '')
            
            energy_log = EnergyManagementService.log_energy_level(
                request.user, energy_level, context_factors, notes
            )
            
            return JsonResponse({
                'success': True,
                'energy_log_id': energy_log.id if energy_log else None
            })
            
        except (ValueError, KeyError, TypeError) as e:
            return JsonResponse({
                'success': False,
                'error': 'Invalid data provided'
            }, status=400)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON format'
            }, status=400)
        except Exception as e:
            logger.error(f'Error in API energy log: {str(e)}')
            return JsonResponse({
                'success': False,
                'error': 'Internal server error'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def api_quick_complete(request, activity_id):
    """API endpoint for quickly completing activities"""
    if request.method == 'POST':
        try:
            activity = get_object_or_404(
                ScheduledActivity, 
                id=activity_id, 
                monk_mode_period__goal__user=request.user
            )
            
            activity.is_completed = True
            activity.completed_at = timezone.now()
            activity.save()
            
            # Update patterns
            try:
                PriorityEngine.update_productivity_patterns(request.user)
            except Exception as e:
                logger.warning(f"Error updating productivity patterns: {str(e)}")
            
            return JsonResponse({
                'success': True,
                'activity_id': activity.id,
                'completed_at': activity.completed_at.isoformat()
            })
            
        except Exception as e:
            logger.error(f'Error in API quick complete: {str(e)}')
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
def api_dashboard_refresh(request):
    """API endpoint for refreshing dashboard data"""
    if request.method == 'GET':
        try:
            user = request.user
            
            # Get essential dashboard data
            active_goals = MonkModeGoal.objects.filter(
                user=user, 
                current_status='active'
            ).prefetch_related('periods')
            
            # Get today's activities
            today_activities = []
            if active_goals.exists():
                active_goal = active_goals.first()
                active_periods = active_goal.periods.filter(is_active=True)
                if active_periods.exists():
                    current_period = active_periods.first()
                    today = timezone.now().date()
                    day_of_period = (today - current_period.start_date).days + 1
                    if day_of_period > 0:
                        today_activities = ScheduledActivity.objects.filter(
                            monk_mode_period=current_period,
                            day_of_period=day_of_period
                        ).select_related('activity_type')
            
            # Get latest energy
            latest_energy = EnergyLog.objects.filter(user=user).order_by('-timestamp').first()
            
            # Calculate metrics
            metrics = {
                'active_goals': active_goals.count(),
                'completed_goals': MonkModeGoal.objects.filter(user=user, current_status='completed').count(),
                'current_streak': _calculate_current_streak(user),
                'avg_mood_week': _calculate_avg_mood(user, 7),
            }
            
            response_data = {
                'success': True,
                'metrics': metrics,
                'today_activities_count': len(today_activities),
                'completed_activities_today': len([a for a in today_activities if a.is_completed]),
                'predicted_energy': latest_energy.energy_level if latest_energy else 5,
                'last_updated': timezone.now().isoformat()
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f'Error in API dashboard refresh: {str(e)}')
            return JsonResponse({
                'success': False,
                'error': 'Error refreshing dashboard data'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# Helper functions with enhanced error handling

def _calculate_current_streak(user):
    """Calculate user's current daily logging streak"""
    try:
        today = timezone.now().date()
        streak = 0
        
        for i in range(365):  # Check up to a year
            check_date = today - timedelta(days=i)
            if UserDailyLog.objects.filter(user=user, log_date=check_date).exists():
                streak += 1
            else:
                break
        
        return streak
    except Exception as e:
        logger.error(f"Error calculating streak for user {user.id}: {str(e)}")
        return 0

def _calculate_avg_mood(user, days):
    """Calculate average mood over specified days"""
    try:
        start_date = timezone.now().date() - timedelta(days=days)
        avg = UserDailyLog.objects.filter(
            user=user,
            log_date__gte=start_date,
            mood_rating__isnull=False
        ).aggregate(avg=Avg('mood_rating'))['avg']
        
        return round(avg, 1) if avg else 0
    except Exception as e:
        logger.error(f"Error calculating avg mood: {str(e)}")
        return 0

def _calculate_avg_adherence(user, days):
    """Calculate average adherence over specified days"""
    try:
        start_date = timezone.now().date() - timedelta(days=days)
        avg = UserDailyLog.objects.filter(
            user=user,
            log_date__gte=start_date,
            adherence_score__isnull=False
        ).aggregate(avg=Avg('adherence_score'))['avg']
        
        return round(avg, 1) if avg else 0
    except Exception as e:
        logger.error(f"Error calculating avg adherence: {str(e)}")
        return 0

def _calculate_goal_progress(goal):
    """Calculate comprehensive progress data for a goal"""
    try:
        total_objectives = goal.objectives.count()
        completed_objectives = goal.objectives.filter(is_completed=True).count()
        
        # Get activities data
        if goal.periods.filter(is_active=True).exists():
            active_period = goal.periods.filter(is_active=True).first()
            total_activities = active_period.activities.count()
            completed_activities = active_period.activities.filter(is_completed=True).count()
            
            # Calculate time progress
            total_days = (active_period.end_date - active_period.start_date).days + 1
            elapsed_days = (timezone.now().date() - active_period.start_date).days + 1
            time_progress = min(100, (elapsed_days / total_days) * 100) if total_days > 0 else 0
        else:
            total_activities = 0
            completed_activities = 0
            time_progress = 0
        
        return {
            'objectives_completion': (completed_objectives / max(1, total_objectives)) * 100,
            'activities_completion': (completed_activities / max(1, total_activities)) * 100,
            'time_progress': time_progress,
            'total_objectives': total_objectives,
            'completed_objectives': completed_objectives,
            'total_activities': total_activities,
            'completed_activities': completed_activities,
        }
    except Exception as e:
        logger.error(f"Error calculating goal progress: {str(e)}")
        return {
            'objectives_completion': 0,
            'activities_completion': 0,
            'time_progress': 0,
            'total_objectives': 0,
            'completed_objectives': 0,
            'total_activities': 0,
            'completed_activities': 0,
        }

def user_logout(request):
    """Proper logout function"""
    try:
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
        messages.error(request, 'Error during logout.')
    
    return redirect('accounts:login')