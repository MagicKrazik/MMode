from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
from apps.core.models import MonkModeGoal, ScheduledActivity, UserDailyLog, MonkModePeriod

@login_required
def dashboard(request):
    today = timezone.now().date()

# Get user's active goal
    active_goal = MonkModeGoal.objects.filter(
        user=request.user,
        current_status='active'
    ).first()

# Get today's activities
    today_activities = []
    active_period = None

    if active_goal:
        active_period = MonkModePeriod.objects.filter(
            goal=active_goal,
            is_active=True
        ).first()

        if active_period:
# Calculate day of period
            day_of_period = (today - active_period.start_date).days + 1
            today_activities = ScheduledActivity.objects.filter(
                monk_mode_period=active_period,
                day_of_period=day_of_period
            ).order_by('start_time')

# Get recent daily logs
    recent_logs = UserDailyLog.objects.filter(
        user=request.user
    ).order_by('-log_date')[:5]

# Calculate progress stats
    total_activities = len(today_activities)
    completed_activities = sum(1 for activity in today_activities if activity.is_completed)

    context = {
        'active_goal': active_goal,
        'active_period': active_period,
        'today_activities': today_activities,
        'recent_logs': recent_logs,
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'completion_percentage': (completed_activities / total_activities * 100) if total_activities > 0 else 0,
    }

    return render(request, 'dashboard/dashboard.html', context)
