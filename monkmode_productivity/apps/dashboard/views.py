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

@login_required
def dashboard(request):
    """Main dashboard view with comprehensive overview"""
    user = request.user
    
    try:
        # Get active goals
        active_goals = MonkModeGoal.objects.filter(user=user, current_status='active')
        
        # Get recent daily logs
        recent_logs = UserDailyLog.objects.filter(user=user).order_by('-log_date')[:7]
        
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
                    ).order_by('start_time')
        
        # Get daily motivation with error handling
        daily_motivation = None
        try:
            daily_motivation = MotivationService.get_daily_motivation(user, 'morning')
        except:
            daily_motivation = {'message': 'Stay focused on your goals today!', 'type': 'text'}
        
        # Get focus recommendations with error handling
        focus_recommendations = []
        try:
            focus_recommendations = PriorityEngine.get_focus_recommendations(user)
        except:
            focus_recommendations = []
        
        # Get energy insights with error handling
        latest_energy = None
        energy_prediction = []
        try:
            latest_energy = EnergyLog.objects.filter(user=user).order_by('-timestamp').first()
            energy_prediction = EnergyManagementService.predict_energy_levels(user, hours_ahead=12)
        except:
            latest_energy = None
            energy_prediction = []
        
        # Calculate dashboard metrics
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
        messages.error(request, f'Dashboard error: {str(e)}')
        context = {
            'active_goals': [],
            'recent_logs': [],
            'today_activities': [],
            'metrics': {'total_goals': 0, 'active_goals': 0, 'completed_goals': 0, 'current_streak': 0},
        }
    
    return render(request, 'dashboard/dashboard.html', context)


@login_required
def goals_list(request):
    """List all user goals with filtering and search"""
    goals = MonkModeGoal.objects.filter(user=request.user).order_by('-created_at')
    
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
                objective = MonkModeObjective.objects.create(
                    goal=goal,
                    description=request.POST['description'],
                    due_date=request.POST.get('due_date') or None,
                    estimated_hours=request.POST.get('estimated_hours') or None,
                    difficulty_level=int(request.POST.get('difficulty_level', 3))
                )
                messages.success(request, f'Objective "{objective.description}" added successfully!')
                return redirect('dashboard:goal_detail', goal_id=goal.id)
                
            except Exception as e:
                messages.error(request, f'Error adding objective: {str(e)}')
        
        elif action == 'complete_objective':
            try:
                objective_id = request.POST.get('objective_id')
                objective = get_object_or_404(MonkModeObjective, id=objective_id, goal=goal)
                objective.mark_completed()
                messages.success(request, 'Objective marked as completed!')
                return redirect('dashboard:goal_detail', goal_id=goal.id)
                
            except Exception as e:
                messages.error(request, f'Error completing objective: {str(e)}')
    
    # Get objectives
    objectives = goal.objectives.all().order_by('due_date', '-created_at')
    
    # Get periods
    periods = goal.periods.all().order_by('-created_at')
    active_period = periods.filter(is_active=True).first()
    
    # Get recent activities if there's an active period
    recent_activities = []
    if active_period:
        recent_activities = ScheduledActivity.objects.filter(
            monk_mode_period=active_period
        ).order_by('-day_of_period', 'start_time')[:20]
    
    # Get progress data
    progress_data = _calculate_goal_progress(goal)
    
    context = {
        'goal': goal,
        'objectives': objectives,
        'periods': periods,
        'active_period': active_period,
        'recent_activities': recent_activities,
        'progress_data': progress_data,
    }
    
    return render(request, 'dashboard/goal_detail.html', context)

@login_required
def create_goal(request):
    """Create a new Monk Mode goal"""
    if request.method == 'POST':
        try:
            goal = MonkModeGoal.objects.create(
                user=request.user,
                title=request.POST['title'],
                description=request.POST['description'],
                start_date=request.POST['start_date'],
                end_date=request.POST['end_date'],
                target_outcome=request.POST['target_outcome'],
                priority_level=request.POST.get('priority_level', 3),
                estimated_effort_hours=request.POST.get('estimated_effort_hours'),
                support_network_enabled=request.POST.get('support_network_enabled') == 'on',
                motivation_reminders_enabled=request.POST.get('motivation_reminders_enabled') == 'on'
            )
            
            messages.success(request, f'Goal "{goal.title}" created successfully!')
            return redirect('dashboard:goal_detail', goal_id=goal.id)
            
        except Exception as e:
            messages.error(request, f'Error creating goal: {str(e)}')
    
    return render(request, 'dashboard/create_goal.html')

@login_required
def ai_chat(request, goal_id=None):
    """AI chat interface for goal planning and assistance"""
    goal = None
    if goal_id:
        goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    
    # Get recent chat history - FIXED: No negative indexing
    chat_history_qs = AIPromptHistory.objects.filter(
        user=request.user,
        monk_mode_goal=goal
    ).order_by('timestamp')
    
    # Get last 20 messages without negative indexing
    chat_history = list(chat_history_qs)[-20:] if chat_history_qs.exists() else []
    
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
                    if response['plan_generated']:
                        messages.success(request, 'AI has generated a new Monk Mode plan for you!')
                        return redirect('dashboard:schedule_view', period_id=response['monk_mode_period_id'])
                    
            except Exception as e:
                error_msg = 'Sorry, there was an error processing your message.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'ai_response': error_msg, 'status': 'error'})
                else:
                    messages.error(request, error_msg)
    
    context = {
        'goal': goal,
        'chat_history': chat_history,
    }
    
    return render(request, 'dashboard/ai_chat.html', context)

@login_required
def schedule_view(request, period_id):
    """View and manage schedule for a specific period"""
    period = get_object_or_404(MonkModePeriod, id=period_id, goal__user=request.user)
    
    # Get activities grouped by day
    activities = ScheduledActivity.objects.filter(
        monk_mode_period=period
    ).order_by('day_of_period', 'start_time')
    
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
    
    return render(request, 'dashboard/schedule_view.html', context)

@login_required
@require_POST
def complete_activity(request, activity_id):
    """Mark an activity as completed"""
    activity = get_object_or_404(ScheduledActivity, id=activity_id, monk_mode_period__goal__user=request.user)
    
    try:
        activity.is_completed = True
        activity.completed_at = timezone.now()
        
        # Get additional data from request
        quality_rating = request.POST.get('quality_rating')
        if quality_rating:
            activity.completion_quality = int(quality_rating)
        
        actual_start = request.POST.get('actual_start_time')
        actual_end = request.POST.get('actual_end_time')
        
        if actual_start:
            activity.actual_start_time = timezone.now().replace(
                hour=int(actual_start.split(':')[0]),
                minute=int(actual_start.split(':')[1]),
                second=0,
                microsecond=0
            )
        
        if actual_end:
            activity.actual_end_time = timezone.now().replace(
                hour=int(actual_end.split(':')[0]),
                minute=int(actual_end.split(':')[1]),
                second=0,
                microsecond=0
            )
        
        activity.save()
        
        # Update productivity patterns
        PriorityEngine.update_productivity_patterns(request.user)
        
        # Check for milestone triggers
        MotivationService.check_milestone_triggers(request.user, activity.monk_mode_period.goal)
        
        messages.success(request, f'Activity "{activity.description}" marked as completed!')
        
    except Exception as e:
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
    daily_log, created = UserDailyLog.objects.get_or_create(
        user=request.user,
        log_date=log_date,
        defaults={}
    )
    
    if request.method == 'POST':
        try:
            # Update daily log fields with proper validation
            daily_log.reflection_text = request.POST.get('reflection_text', '')
            
            # Handle numeric fields with validation
            adherence_score = request.POST.get('adherence_score')
            if adherence_score and adherence_score.strip():
                daily_log.adherence_score = max(1, min(10, int(adherence_score)))
            
            mood_rating = request.POST.get('mood_rating')
            if mood_rating and mood_rating.strip():
                daily_log.mood_rating = max(1, min(5, int(mood_rating)))
            
            energy_morning = request.POST.get('energy_morning')
            if energy_morning and energy_morning.strip():
                daily_log.energy_level_morning = max(1, min(10, int(energy_morning)))
            
            energy_afternoon = request.POST.get('energy_afternoon')
            if energy_afternoon and energy_afternoon.strip():
                daily_log.energy_level_afternoon = max(1, min(10, int(energy_afternoon)))
            
            energy_evening = request.POST.get('energy_evening')
            if energy_evening and energy_evening.strip():
                daily_log.energy_level_evening = max(1, min(10, int(energy_evening)))
            
            sleep_quality = request.POST.get('sleep_quality')
            if sleep_quality and sleep_quality.strip():
                daily_log.sleep_quality = max(1, min(5, int(sleep_quality)))
            
            stress_level = request.POST.get('stress_level')
            if stress_level and stress_level.strip():
                daily_log.stress_level = max(1, min(5, int(stress_level)))
            
            environment_rating = request.POST.get('environment_rating')
            if environment_rating and environment_rating.strip():
                daily_log.environment_rating = max(1, min(5, int(environment_rating)))
            
            distractions_count = request.POST.get('distractions_count')
            if distractions_count and distractions_count.strip():
                daily_log.distractions_count = max(0, int(distractions_count))
            
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
                except:
                    pass  # Don't fail the entire save if energy logging fails
            
            # Check for support triggers
            if daily_log.mood_rating and daily_log.mood_rating <= 2:
                try:
                    SupportNetworkService.check_mood_triggers(request.user)
                except:
                    pass
            
            if daily_log.adherence_score and daily_log.adherence_score <= 5:
                try:
                    SupportNetworkService.check_adherence_triggers(request.user)
                except:
                    pass
            
            messages.success(request, 'Daily log updated successfully!')
            
        except ValueError as e:
            messages.error(request, 'Please enter valid numbers for ratings and scores.')
        except Exception as e:
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
                    ).order_by('start_time')
    except:
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
    contacts = SupportContact.objects.filter(user=request.user, is_active=True).order_by('name')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_contact':
            try:
                SupportContact.objects.create(
                    user=request.user,
                    name=request.POST['name'],
                    email=request.POST['email'],
                    phone=request.POST.get('phone', ''),
                    relationship=request.POST['relationship'],
                    emergency_contact=request.POST.get('emergency_contact') == 'on',
                    notification_preferences=json.loads(request.POST.get('preferences', '{}'))
                )
                messages.success(request, 'Support contact added successfully!')
                
            except Exception as e:
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
                messages.error(request, f'Error sending support request: {str(e)}')
    
    # Get recent notifications
    recent_notifications = SupportNotification.objects.filter(
        user=request.user
    ).order_by('-sent_at')[:10]
    
    context = {
        'contacts': contacts,
        'recent_notifications': recent_notifications,
    }
    
    return render(request, 'dashboard/support_network.html', context)

@login_required
def motivation_center(request):
    """Motivation and commitment management center"""
    user = request.user
    
    # Get user's motivation content
    motivation_media = MotivationMedia.objects.filter(user=user).order_by('-created_at')
    self_letters = SelfLetter.objects.filter(user=user).order_by('-created_at')
    commitments = UserCommitment.objects.filter(user=user, is_active=True)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'upload_media':
            try:
                media_data = {
                    'media_type': request.POST['media_type'],
                    'title': request.POST['title'],
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
                messages.error(request, f'Error uploading media: {str(e)}')
        
        elif action == 'schedule_letter':
            try:
                letter_data = {
                    'subject': request.POST['subject'],
                    'content': request.POST['content'],
                    'delivery_trigger': request.POST['delivery_trigger'],
                    'goal_id': request.POST.get('goal_id'),
                }
                
                if request.POST['delivery_trigger'] == 'scheduled':
                    letter_data['delivery_date'] = datetime.strptime(
                        request.POST['delivery_date'], '%Y-%m-%d %H:%M'
                    )
                
                letter = MotivationService.schedule_letter_delivery(user, letter_data)
                if letter:
                    messages.success(request, 'Letter scheduled successfully!')
                else:
                    messages.error(request, 'Error scheduling letter.')
                    
            except Exception as e:
                messages.error(request, f'Error scheduling letter: {str(e)}')
        
        elif action == 'create_commitment':
            try:
                active_goal = MonkModeGoal.objects.filter(user=user, current_status='active').first()
                if active_goal:
                    commitment_data = {
                        'commitment_text': request.POST['commitment_text'],
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
                messages.error(request, f'Error creating commitment: {str(e)}')
    
    # Get daily motivation
    daily_motivation = MotivationService.get_daily_motivation(user)
    
    # Get user's active goals for letter scheduling
    active_goals = MonkModeGoal.objects.filter(user=user, current_status='active')
    
    context = {
        'motivation_media': motivation_media[:10],
        'self_letters': self_letters[:10],
        'commitments': commitments,
        'daily_motivation': daily_motivation,
        'active_goals': active_goals,
    }
    
    return render(request, 'dashboard/motivation_center.html', context)

@login_required
def priority_focus(request):
    """Task prioritization and focus recommendations"""
    user = request.user
    
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
                messages.error(request, f'Error getting AI recommendations: {str(e)}')
    
    context = {
        'focus_recommendations': focus_recommendations,
        'prioritized_activities': prioritized_activities,
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
                energy_level = int(request.POST['energy_level'])
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
                    
            except Exception as e:
                messages.error(request, f'Error logging energy: {str(e)}')
    
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
        'predictions': predictions[:12],  # Next 12 hours
        'recovery_recommendations': recovery_recommendations,
    }
    
    return render(request, 'dashboard/energy_tracking.html', context)

@login_required
def progress_analytics(request):
    """Comprehensive progress analytics and insights"""
    user = request.user
    
    # Time period filter
    days_back = int(request.GET.get('days', 30))
    
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
    
    # Calculate analytics
    analytics = {
        'total_goals': goals.count(),
        'active_goals': active_goals.count(),
        'completed_goals': completed_goals.count(),
        'goal_completion_rate': (completed_goals.count() / max(1, goals.count())) * 100,
        'avg_mood': daily_logs.aggregate(avg=Avg('mood_rating'))['avg'] or 0,
        'avg_adherence': daily_logs.aggregate(avg=Avg('adherence_score'))['avg'] or 0,
        'avg_energy': daily_logs.aggregate(avg=Avg('energy_level_morning'))['avg'] or 0,
        'total_activities_completed': ScheduledActivity.objects.filter(
            monk_mode_period__goal__user=user,
            is_completed=True,
            completed_at__gte=datetime.combine(start_date, datetime.min.time())
        ).count(),
        'streak': _calculate_current_streak(user),
    }
    
    # Get weekly AI insights
    weekly_insights = AIService.generate_weekly_review_insights(user)
    
    context = {
        'analytics': analytics,
        'daily_logs': daily_logs,
        'active_goals': active_goals,
        'completed_goals': completed_goals,
        'weekly_insights': weekly_insights,
        'days_back': days_back,
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
            emergency_motivation = MotivationService.trigger_mood_motivation(request.user)
            
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
            energy_level = data['energy_level']
            context_factors = data.get('context_factors', {})
            notes = data.get('notes', '')
            
            energy_log = EnergyManagementService.log_energy_level(
                request.user, energy_level, context_factors, notes
            )
            
            return JsonResponse({
                'success': True,
                'energy_log_id': energy_log.id if energy_log else None
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
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
            PriorityEngine.update_productivity_patterns(request.user)
            
            return JsonResponse({
                'success': True,
                'activity_id': activity.id,
                'completed_at': activity.completed_at.isoformat()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# Helper functions

def _calculate_current_streak(user):
    """Calculate user's current daily logging streak"""
    today = timezone.now().date()
    streak = 0
    
    for i in range(365):  # Check up to a year
        check_date = today - timedelta(days=i)
        if UserDailyLog.objects.filter(user=user, log_date=check_date).exists():
            streak += 1
        else:
            break
    
    return streak

def _calculate_avg_mood(user, days):
    """Calculate average mood over specified days"""
    start_date = timezone.now().date() - timedelta(days=days)
    avg = UserDailyLog.objects.filter(
        user=user,
        log_date__gte=start_date,
        mood_rating__isnull=False
    ).aggregate(avg=Avg('mood_rating'))['avg']
    
    return round(avg, 1) if avg else 0

def _calculate_avg_adherence(user, days):
    """Calculate average adherence over specified days"""
    start_date = timezone.now().date() - timedelta(days=days)
    avg = UserDailyLog.objects.filter(
        user=user,
        log_date__gte=start_date,
        adherence_score__isnull=False
    ).aggregate(avg=Avg('adherence_score'))['avg']
    
    return round(avg, 1) if avg else 0

def _calculate_goal_progress(goal):
    """Calculate comprehensive progress data for a goal"""
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

def user_logout(request):
    """Proper logout function"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('accounts:login')  # Adjust this to your login URL name

