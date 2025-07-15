from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
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
def goal_list(request):
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
        'total_goals': goals.count(),
    }
    
    return render(request, 'core/goal_list.html', context)

@login_required
def goal_create(request):
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
                priority_level=int(request.POST.get('priority_level', 3)),
                estimated_effort_hours=int(request.POST['estimated_effort_hours']) if request.POST.get('estimated_effort_hours') else None,
                support_network_enabled=request.POST.get('support_network_enabled') == 'on',
                motivation_reminders_enabled=request.POST.get('motivation_reminders_enabled') == 'on'
            )
            
            messages.success(request, f'Goal "{goal.title}" created successfully!')
            return redirect('core:goal_detail', goal_id=goal.id)
            
        except Exception as e:
            messages.error(request, f'Error creating goal: {str(e)}')
    
    return render(request, 'core/goal_create.html')

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
                    due_date=datetime.strptime(request.POST['due_date'], '%Y-%m-%d').date() if request.POST.get('due_date') else None,
                    estimated_hours=int(request.POST['estimated_hours']) if request.POST.get('estimated_hours') else None,
                    difficulty_level=int(request.POST.get('difficulty_level', 3))
                )
                messages.success(request, f'Objective "{objective.description}" added successfully!')
                return redirect('core:goal_detail', goal_id=goal.id)
                
            except Exception as e:
                messages.error(request, f'Error adding objective: {str(e)}')
        
        elif action == 'complete_objective':
            try:
                objective_id = request.POST.get('objective_id')
                objective = get_object_or_404(MonkModeObjective, id=objective_id, goal=goal)
                objective.mark_completed()
                messages.success(request, 'Objective marked as completed!')
                return redirect('core:goal_detail', goal_id=goal.id)
                
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
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/goal_detail.html', context)

@login_required
def goal_edit(request, goal_id):
    """Edit an existing goal"""
    goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    
    if request.method == 'POST':
        try:
            goal.title = request.POST['title']
            goal.description = request.POST['description']
            goal.start_date = request.POST['start_date']
            goal.end_date = request.POST['end_date']
            goal.target_outcome = request.POST['target_outcome']
            goal.priority_level = int(request.POST.get('priority_level', 3))
            goal.estimated_effort_hours = int(request.POST['estimated_effort_hours']) if request.POST.get('estimated_effort_hours') else None
            goal.support_network_enabled = request.POST.get('support_network_enabled') == 'on'
            goal.motivation_reminders_enabled = request.POST.get('motivation_reminders_enabled') == 'on'
            goal.save()
            
            messages.success(request, 'Goal updated successfully!')
            return redirect('core:goal_detail', goal_id=goal.id)
            
        except Exception as e:
            messages.error(request, f'Error updating goal: {str(e)}')
    
    context = {'goal': goal}
    return render(request, 'core/goal_edit.html', context)

@login_required
def generate_schedule(request, goal_id):
    """Generate AI schedule for a goal"""
    goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    
    if request.method == 'POST':
        try:
            # Get user input for schedule preferences
            schedule_preferences = {
                'start_date': request.POST.get('start_date', goal.start_date.strftime('%Y-%m-%d')),
                'end_date': request.POST.get('end_date', goal.end_date.strftime('%Y-%m-%d')),
                'daily_hours': request.POST.get('daily_hours', '8'),
                'break_frequency': request.POST.get('break_frequency', '60'),
                'energy_preference': request.POST.get('energy_preference', 'morning'),
                'focus_blocks': request.POST.get('focus_blocks', '2'),
            }
            
            # Generate AI schedule request
            ai_message = f"""
            Please generate a detailed Monk Mode schedule for my goal: "{goal.title}"
            
            Goal description: {goal.description}
            Target outcome: {goal.target_outcome}
            
            Schedule preferences:
            - Start date: {schedule_preferences['start_date']}
            - End date: {schedule_preferences['end_date']}
            - Daily working hours: {schedule_preferences['daily_hours']}
            - Break every: {schedule_preferences['break_frequency']} minutes
            - Peak energy time: {schedule_preferences['energy_preference']}
            - Deep work blocks per day: {schedule_preferences['focus_blocks']}
            
            Please create a comprehensive daily schedule with specific time blocks for:
            - Deep work sessions
            - Learning and skill development
            - Exercise and wellness
            - Meals and breaks
            - Reflection time
            - Sleep schedule
            
            Format the response as a structured JSON plan that I can follow.
            """
            
            response = AIService.send_message_to_gemini(
                request.user.id,
                goal.id,
                ai_message,
                message_type='plan_generation'
            )
            
            if response['plan_generated']:
                messages.success(request, 'AI schedule generated successfully!')
                return redirect('core:schedule_view', period_id=response['monk_mode_period_id'])
            else:
                messages.info(request, 'Schedule request sent to AI. You can continue the conversation in the chat.')
                return redirect('dashboard:ai_chat', goal_id=goal.id)
                
        except Exception as e:
            messages.error(request, f'Error generating schedule: {str(e)}')
    
    context = {
        'goal': goal,
        'suggested_start_date': goal.start_date.strftime('%Y-%m-%d'),
        'suggested_end_date': goal.end_date.strftime('%Y-%m-%d'),
    }
    
    return render(request, 'core/generate_schedule.html', context)

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
    
    # Calculate completion stats
    total_activities = activities.count()
    completed_activities = activities.filter(is_completed=True).count()
    completion_percentage = (completed_activities / max(1, total_activities)) * 100
    
    context = {
        'period': period,
        'activities_by_day': activities_by_day,
        'current_day': current_day,
        'total_days': (period.end_date - period.start_date).days + 1,
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'completion_percentage': completion_percentage,
    }
    
    return render(request, 'core/schedule_view.html', context)

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
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/daily_log.html', context)

@login_required
@require_POST
def mark_activity_complete(request, activity_id):
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
        try:
            PriorityEngine.update_productivity_patterns(request.user)
        except:
            pass
        
        # Check for milestone triggers
        try:
            MotivationService.check_milestone_triggers(request.user, activity.monk_mode_period.goal)
        except:
            pass
        
        messages.success(request, f'Activity "{activity.description or activity.activity_type.name}" marked as completed!')
        
    except Exception as e:
        messages.error(request, f'Error completing activity: {str(e)}')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect('core:schedule_view', period_id=activity.monk_mode_period.id)

# Helper functions
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
    except:
        return {
            'objectives_completion': 0,
            'activities_completion': 0,
            'time_progress': 0,
            'total_objectives': 0,
            'completed_objectives': 0,
            'total_activities': 0,
            'completed_activities': 0,
        }