from django.contrib import admin
from .models import MonkModeGoal, MonkModeObjective, ActivityType, MonkModePeriod, ScheduledActivity, UserDailyLog

@admin.register(MonkModeGoal)
class MonkModeGoalAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'current_status', 'start_date', 'end_date', 'created_at']
    list_filter = ['current_status', 'created_at']
    search_fields = ['title', 'user__username']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(MonkModeObjective)
class MonkModeObjectiveAdmin(admin.ModelAdmin):
    list_display = ['description', 'goal', 'due_date', 'is_completed']
    list_filter = ['is_completed', 'due_date']
    search_fields = ['description', 'goal__title']

@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'default_duration_minutes', 'is_core_monk_mode']
    list_filter = ['is_core_monk_mode']

@admin.register(MonkModePeriod)
class MonkModePeriodAdmin(admin.ModelAdmin):
    list_display = ['period_name', 'goal', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active', 'created_at']

@admin.register(ScheduledActivity)
class ScheduledActivityAdmin(admin.ModelAdmin):
    list_display = ['activity_type', 'monk_mode_period', 'day_of_period', 'start_time', 'is_completed']
    list_filter = ['is_completed', 'activity_type']

@admin.register(UserDailyLog)
class UserDailyLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'log_date', 'adherence_score', 'mood_rating']
    list_filter = ['log_date', 'adherence_score', 'mood_rating']
    search_fields = ['user__username']
