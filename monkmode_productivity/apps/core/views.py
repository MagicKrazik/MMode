from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, timedelta
from .models import MonkModeGoal, MonkModeObjective, ScheduledActivity, UserDailyLog, MonkModePeriod
from .forms import MonkModeGoalForm, MonkModeObjectiveForm, UserDailyLogForm
from .utils import generate_basic_schedule

@login_required
def goal_list(request):
    goals = MonkModeGoal.objects.filter(user=request.user)
    return render(request, 'core/goal_list.html', {'goals': goals})

@login_required
def goal_detail(request, goal_id):
    goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    objectives = goal.objectives.all()
    periods = goal.periods.all()
    return render(request, 'core/goal_detail.html', {
        'goal': goal,
        'objectives': objectives,
        'periods': periods
    })

@login_required
def goal_create(request):
    if request.method == 'POST':
        form = MonkModeGoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, 'Goal created successfully!')
            return redirect('core:goal_detail', goal_id=goal.id)
    else:
        form = MonkModeGoalForm()
    return render(request, 'core/goal_form.html', {'form': form, 'title': 'Create New Goal'})

@login_required
def goal_edit(request, goal_id):
    goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)
    if request.method == 'POST':
        form = MonkModeGoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, 'Goal updated successfully!')
            return redirect('core:goal_detail', goal_id=goal.id)
    else:
        form = MonkModeGoalForm(instance=goal)
    return render(request, 'core/goal_form.html', {'form': form, 'title': 'Edit Goal', 'goal': goal})

@login_required
def generate_schedule(request, goal_id):
    goal = get_object_or_404(MonkModeGoal, id=goal_id, user=request.user)

    if request.method == 'POST':
# Generate a basic schedule
        period = generate_basic_schedule(goal)
        messages.success(request, f'Schedule generated for {period.period_name}!')
        return redirect('core:schedule_view', period_id=period.id)

    return render(request, 'core/generate_schedule.html', {'goal': goal})

@login_required
def schedule_view(request, period_id):
    period = get_object_or_404(MonkModePeriod, id=period_id, goal__user=request.user)
    activities = period.activities.all()

# Group activities by day
    activities_by_day = {}
    for activity in activities:
        day = activity.day_of_period
        if day not in activities_by_day:
            activities_by_day[day] = []
        activities_by_day[day].append(activity)

    return render(request, 'core/schedule_view.html', {
        'period': period,
        'activities_by_day': activities_by_day
    })

@login_required
def daily_log(request):
    today = timezone.now().date()
    log, created = UserDailyLog.objects.get_or_create(
        user=request.user,
        log_date=today,
        defaults={'reflection_text': ''}
    )

    if request.method == 'POST':
        form = UserDailyLogForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            messages.success(request, 'Daily log saved!')
            return redirect('dashboard:dashboard')
    else:
        form = UserDailyLogForm(instance=log)

    return render(request, 'core/daily_log.html', {'form': form, 'log': log})

@login_required
def mark_activity_complete(request, activity_id):
    activity = get_object_or_404(ScheduledActivity, id=activity_id, monk_mode_period__goal__user=request.user)

    if request.method == 'POST':
        activity.is_completed = True
        activity.completed_at = timezone.now()
        activity.save()
        messages.success(request, f'{activity.activity_type.name} marked as complete!')

    return redirect('core:schedule_view', period_id=activity.monk_mode_period.id)
