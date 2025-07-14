from django.contrib import admin
from .models import (
    MonkModeGoal, MonkModeObjective, MonkModePeriod, ActivityType,
    ScheduledActivity, UserDailyLog, AIPromptHistory, SupportContact,
    SupportNotification, UserCommitment, MotivationMedia, SelfLetter,
    TaskPriorityScore, UserProductivityPattern, EnergyLog, EnergyPrediction,
    HabitStack, HabitCompletion, EnvironmentSetting
)

@admin.register(MonkModeGoal)
class MonkModeGoalAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'current_status', 'start_date', 'end_date', 'completion_percentage']
    list_filter = ['current_status', 'priority_level', 'created_at']
    search_fields = ['title', 'description', 'user__username']
    date_hierarchy = 'created_at'
    readonly_fields = ['completion_percentage']

@admin.register(MonkModeObjective)
class MonkModeObjectiveAdmin(admin.ModelAdmin):
    list_display = ['description', 'goal', 'due_date', 'is_completed', 'priority_score']
    list_filter = ['is_completed', 'difficulty_level', 'created_at']
    search_fields = ['description', 'goal__title']
    date_hierarchy = 'created_at'

@admin.register(MonkModePeriod)
class MonkModePeriodAdmin(admin.ModelAdmin):
    list_display = ['period_name', 'goal', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['period_name', 'goal__title']
    date_hierarchy = 'created_at'

@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_core_monk_mode', 'energy_requirement', 'default_duration_minutes']
    list_filter = ['is_core_monk_mode', 'category', 'energy_requirement']
    search_fields = ['name', 'description']

@admin.register(ScheduledActivity)
class ScheduledActivityAdmin(admin.ModelAdmin):
    list_display = ['activity_type', 'monk_mode_period', 'day_of_period', 'start_time', 'is_completed', 'priority_score']
    list_filter = ['is_completed', 'activity_type', 'energy_required', 'completion_quality']
    search_fields = ['description', 'activity_type__name']
    date_hierarchy = 'created_at'

@admin.register(UserDailyLog)
class UserDailyLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'log_date', 'mood_rating', 'adherence_score', 'energy_level_morning']
    list_filter = ['mood_rating', 'adherence_score', 'sleep_quality', 'stress_level']
    search_fields = ['user__username', 'reflection_text']
    date_hierarchy = 'log_date'

@admin.register(AIPromptHistory)
class AIPromptHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'message_type', 'timestamp']
    list_filter = ['role', 'message_type', 'timestamp']
    search_fields = ['user__username', 'message_text']
    date_hierarchy = 'timestamp'

@admin.register(SupportContact)
class SupportContactAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'relationship', 'email', 'is_active', 'emergency_contact']
    list_filter = ['relationship', 'is_active', 'emergency_contact']
    search_fields = ['name', 'email', 'user__username']

@admin.register(SupportNotification)
class SupportNotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'support_contact', 'trigger_type', 'sent_at', 'response_received']
    list_filter = ['trigger_type', 'response_received', 'sent_at']
    search_fields = ['user__username', 'support_contact__name']
    date_hierarchy = 'sent_at'

@admin.register(UserCommitment)
class UserCommitmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'monk_mode_goal', 'public_commitment', 'is_active', 'signed_date']
    list_filter = ['public_commitment', 'is_active', 'signed_date']
    search_fields = ['user__username', 'commitment_text']

@admin.register(MotivationMedia)
class MotivationMediaAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'media_type', 'effectiveness_rating', 'last_shown']
    list_filter = ['media_type', 'effectiveness_rating', 'created_at']
    search_fields = ['user__username', 'title', 'description']

@admin.register(SelfLetter)
class SelfLetterAdmin(admin.ModelAdmin):
    list_display = ['user', 'subject', 'delivery_trigger', 'is_delivered', 'delivery_date']
    list_filter = ['delivery_trigger', 'is_delivered', 'created_at']
    search_fields = ['user__username', 'subject', 'content']

@admin.register(TaskPriorityScore)
class TaskPriorityScoreAdmin(admin.ModelAdmin):
    list_display = ['scheduled_activity', 'final_score', 'deadline_urgency', 'goal_impact', 'calculated_at']
    list_filter = ['final_score', 'calculated_at']
    search_fields = ['scheduled_activity__description']

@admin.register(UserProductivityPattern)
class UserProductivityPatternAdmin(admin.ModelAdmin):
    list_display = ['user', 'hour_of_day', 'activity_type', 'average_performance', 'sample_size']
    list_filter = ['hour_of_day', 'activity_type', 'average_performance']
    search_fields = ['user__username', 'activity_type__name']

@admin.register(EnergyLog)
class EnergyLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'energy_level', 'activity_before']
    list_filter = ['energy_level', 'activity_before', 'timestamp']
    search_fields = ['user__username', 'notes']
    date_hierarchy = 'timestamp'

@admin.register(EnergyPrediction)
class EnergyPredictionAdmin(admin.ModelAdmin):
    list_display = ['user', 'predicted_for', 'predicted_energy', 'confidence_score', 'actual_energy']
    list_filter = ['predicted_for', 'confidence_score']
    search_fields = ['user__username']
    date_hierarchy = 'predicted_for'

@admin.register(HabitStack)
class HabitStackAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'trigger_activity', 'is_active']
    list_filter = ['is_active', 'trigger_activity']
    search_fields = ['user__username', 'name', 'description']

@admin.register(HabitCompletion)
class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ['habit_stack', 'completion_date', 'completion_percentage']
    list_filter = ['completion_date', 'completion_percentage']
    search_fields = ['habit_stack__name']
    date_hierarchy = 'completion_date'

@admin.register(EnvironmentSetting)
class EnvironmentSettingAdmin(admin.ModelAdmin):
    list_display = ['user', 'setting_name', 'is_active', 'effectiveness_rating']
    list_filter = ['is_active', 'effectiveness_rating']
    search_fields = ['user__username', 'setting_name', 'description']