from datetime import datetime, timedelta, time
from .models import MonkModePeriod, ScheduledActivity, ActivityType

def generate_basic_schedule(goal):
    """Generate a basic MonkMode schedule for a goal"""

# Create or get activity types
    activity_types = {
        'Sleep': ActivityType.objects.get_or_create(
            name='Sleep',
            defaults={'default_duration_minutes': 480, 'description': 'Restorative sleep'}
        )[0],
        'Deep Work': ActivityType.objects.get_or_create(
            name='Deep Work',
            defaults={'default_duration_minutes': 240, 'description': 'Focused work on main goal'}
        )[0],
        'Exercise': ActivityType.objects.get_or_create(
            name='Exercise',
            defaults={'default_duration_minutes': 60, 'description': 'Physical activity'}
        )[0],
        'Mindfulness': ActivityType.objects.get_or_create(
            name='Mindfulness',
            defaults={'default_duration_minutes': 15, 'description': 'Meditation or mindfulness practice'}
        )[0],
        'Cooking': ActivityType.objects.get_or_create(
            name='Cooking',
            defaults={'default_duration_minutes': 30, 'description': 'Meal preparation'}
        )[0],
        'Partner Time': ActivityType.objects.get_or_create(
            name='Partner Time',
            defaults={'default_duration_minutes': 90, 'description': 'Quality time with partner/family'}
        )[0],
        'Reflection': ActivityType.objects.get_or_create(
            name='Reflection',
            defaults={'default_duration_minutes': 15, 'description': 'Daily reflection and journaling'}
        )[0],
    }

# Create MonkMode period
    period = MonkModePeriod.objects.create(
        goal=goal,
        period_name=f"{goal.title} - Basic Schedule",
        start_date=goal.start_date,
        end_date=goal.end_date,
        is_active=True
    )

# Deactivate other periods for this goal
    MonkModePeriod.objects.filter(goal=goal).exclude(id=period.id).update(is_active=False)

# Basic daily schedule template
    daily_schedule = [
        ('Sleep', time(0, 0), time(7, 0)),
        ('Mindfulness', time(7, 0), time(7, 15)),
        ('Exercise', time(7, 15), time(8, 15)),
        ('Cooking', time(8, 15), time(8, 45)),
        ('Deep Work', time(9, 0), time(12, 0)),
        ('Cooking', time(12, 0), time(12, 30)),
        ('Deep Work', time(13, 0), time(16, 0)),
        ('Exercise', time(16, 0), time(17, 0)),
        ('Cooking', time(17, 0), time(17, 30)),
        ('Partner Time', time(18, 0), time(20, 0)),
        ('Reflection', time(20, 0), time(20, 15)),
        ('Sleep', time(23, 0), time(23, 59)),
    ]

# Generate activities for each day
    total_days = (goal.end_date - goal.start_date).days + 1

    for day in range(1, total_days + 1):
        for activity_name, start_time, end_time in daily_schedule:
# Calculate duration
            start_minutes = start_time.hour * 60 + start_time.minute
            end_minutes = end_time.hour * 60 + end_time.minute

# Handle overnight activities
            if end_minutes < start_minutes:
                end_minutes += 24 * 60

            duration = end_minutes - start_minutes

            ScheduledActivity.objects.create(
                monk_mode_period=period,
                activity_type=activity_types[activity_name],
                day_of_period=day,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration,
                description=f"Day {day} - {activity_name}"
            )

    return period
