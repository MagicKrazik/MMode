from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import json

class MonkModeGoal(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='monk_mode_goals')
    title = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    target_outcome = models.TextField()
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # V2 Enhancements
    priority_level = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    estimated_effort_hours = models.IntegerField(null=True, blank=True)
    support_network_enabled = models.BooleanField(default=True)
    motivation_reminders_enabled = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    @property
    def completion_percentage(self):
        total_objectives = self.objectives.count()
        if total_objectives == 0:
            return 0
        completed_objectives = self.objectives.filter(is_completed=True).count()
        return (completed_objectives / total_objectives) * 100

class MonkModeObjective(models.Model):
    goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE, related_name='objectives')
    description = models.TextField()
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # V2 Enhancements
    priority_score = models.FloatField(default=0.0)
    estimated_hours = models.IntegerField(null=True, blank=True)
    difficulty_level = models.IntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)])
    dependencies = models.ManyToManyField('self', blank=True, symmetrical=False)
    
    def __str__(self):
        return f"{self.goal.title} - {self.description[:50]}"
    
    def mark_completed(self):
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save()

class MonkModePeriod(models.Model):
    goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE, related_name='periods')
    period_name = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    ai_generated_json = models.JSONField(default=dict)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.goal.title} - {self.period_name}"
    
    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate other periods for the same goal
            MonkModePeriod.objects.filter(goal=self.goal, is_active=True).update(is_active=False)
        super().save(*args, **kwargs)

class ActivityType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    default_duration_minutes = models.IntegerField(null=True, blank=True)
    is_core_monk_mode = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # V2 Enhancements
    energy_requirement = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    category = models.CharField(max_length=50, default='work')
    color_code = models.CharField(max_length=7, default='#3498db')  # Hex color
    
    def __str__(self):
        return self.name

class ScheduledActivity(models.Model):
    monk_mode_period = models.ForeignKey(MonkModePeriod, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE)
    day_of_period = models.IntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    duration_minutes = models.IntegerField()
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # V2 Enhancements
    priority_score = models.FloatField(default=0.0)
    energy_required = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    completion_quality = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    
    def __str__(self):
        return f"Day {self.day_of_period} - {self.activity_type.name}"
    
    @property
    def actual_duration_minutes(self):
        if self.actual_start_time and self.actual_end_time:
            return int((self.actual_end_time - self.actual_start_time).total_seconds() / 60)
        return None

class UserDailyLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_logs')
    log_date = models.DateField()
    monk_mode_period = models.ForeignKey(MonkModePeriod, on_delete=models.SET_NULL, null=True, blank=True)
    reflection_text = models.TextField(blank=True)
    adherence_score = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    mood_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # V2 Enhancements
    energy_level_morning = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    energy_level_afternoon = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    energy_level_evening = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])
    sleep_quality = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    stress_level = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    environment_rating = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    distractions_count = models.IntegerField(default=0)
    wins_of_the_day = models.TextField(blank=True)
    challenges_faced = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['user', 'log_date']
        ordering = ['-log_date']
    
    def __str__(self):
        return f"{self.user.username} - {self.log_date}"

class AIPromptHistory(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('model', 'AI Model'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_conversations')
    monk_mode_goal = models.ForeignKey(MonkModeGoal, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    message_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # V2 Enhancements
    session_id = models.CharField(max_length=100, null=True, blank=True)
    message_type = models.CharField(max_length=50, default='chat')  # chat, plan_generation, priority_request
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.user.username} - {self.role} - {self.timestamp}"

# V2 New Models

class SupportContact(models.Model):
    RELATIONSHIP_CHOICES = [
        ('family', 'Family Member'),
        ('friend', 'Friend'),
        ('mentor', 'Mentor'),
        ('coach', 'Coach'),
        ('partner', 'Life Partner'),
        ('colleague', 'Colleague'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_contacts')
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES)
    notification_preferences = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    emergency_contact = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.relationship})"

class SupportNotification(models.Model):
    TRIGGER_CHOICES = [
        ('mood_low', 'Low Mood Rating'),
        ('missed_activities', 'Missed Activities'),
        ('adherence_drop', 'Adherence Drop'),
        ('user_request', 'User Request'),
        ('emergency', 'Emergency'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    support_contact = models.ForeignKey(SupportContact, on_delete=models.CASCADE)
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    message_template = models.TextField()
    sent_at = models.DateTimeField()
    response_received = models.BooleanField(default=False)
    response_text = models.TextField(blank=True)
    response_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Alert to {self.support_contact.name} - {self.trigger_type}"

class UserCommitment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commitments')
    monk_mode_goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE)
    commitment_text = models.TextField()
    consequences = models.TextField()
    reward_for_success = models.TextField()
    public_commitment = models.BooleanField(default=False)
    signed_date = models.DateTimeField(auto_now_add=True)
    witness_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.monk_mode_goal.title}"

class MotivationMedia(models.Model):
    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('text', 'Text Note'),
    ]
    
    TRIGGER_CHOICES = [
        ('mood_low', 'When Mood is Low'),
        ('morning', 'Morning Motivation'),
        ('evening', 'Evening Reflection'),
        ('before_deep_work', 'Before Deep Work'),
        ('milestone', 'Milestone Achievement'),
        ('random', 'Random Reminders'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='motivation_media')
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    file_path = models.FileField(upload_to='motivation/', null=True, blank=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    text_content = models.TextField(blank=True)  # For text type motivation
    display_triggers = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    last_shown = models.DateTimeField(null=True, blank=True)
    effectiveness_rating = models.FloatField(default=0.0)
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"

class SelfLetter(models.Model):
    DELIVERY_TRIGGER_CHOICES = [
        ('scheduled', 'Scheduled Date'),
        ('milestone', 'Milestone Achievement'),
        ('mood_low', 'When Feeling Down'),
        ('completion', 'Goal Completion'),
        ('halfway', 'Halfway Point'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='self_letters')
    monk_mode_goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.CharField(max_length=200)
    content = models.TextField()
    delivery_date = models.DateTimeField(null=True, blank=True)
    delivery_trigger = models.CharField(max_length=20, choices=DELIVERY_TRIGGER_CHOICES)
    is_delivered = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.subject}"

class TaskPriorityScore(models.Model):
    scheduled_activity = models.OneToOneField('ScheduledActivity', on_delete=models.CASCADE, related_name='task_priority_score')
    deadline_urgency = models.FloatField(default=0.0)
    goal_impact = models.FloatField(default=0.0)
    energy_requirement = models.FloatField(default=0.0)
    dependency_weight = models.FloatField(default=0.0)
    user_preference = models.FloatField(default=0.0)
    momentum_factor = models.FloatField(default=0.0)
    final_score = models.FloatField(default=0.0)
    calculated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Priority: {self.final_score:.2f} - {self.scheduled_activity}"

class UserProductivityPattern(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='productivity_patterns')
    hour_of_day = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(23)])
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE)
    average_performance = models.FloatField(default=0.0)
    energy_level = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0)
    sample_size = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'hour_of_day', 'activity_type']
    
    def __str__(self):
        return f"{self.user.username} - {self.hour_of_day}:00 - {self.activity_type.name}"

class EnergyLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='energy_logs')
    timestamp = models.DateTimeField()
    energy_level = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    activity_before = models.ForeignKey(ActivityType, on_delete=models.SET_NULL, null=True, blank=True)
    context_factors = models.JSONField(default=dict)  # sleep, food, stress, weather, etc.
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} - {self.timestamp} - Energy: {self.energy_level}"

class EnergyPrediction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='energy_predictions')
    predicted_for = models.DateTimeField()
    predicted_energy = models.FloatField()
    confidence_score = models.FloatField()
    actual_energy = models.FloatField(null=True, blank=True)
    prediction_accuracy = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.predicted_for} - Predicted: {self.predicted_energy}"

class HabitStack(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='habit_stacks')
    monk_mode_goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField()
    trigger_activity = models.ForeignKey(ActivityType, on_delete=models.CASCADE, related_name='triggered_habits')
    habits = models.JSONField(default=list)  # List of micro-habits
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"

class HabitCompletion(models.Model):
    habit_stack = models.ForeignKey(HabitStack, on_delete=models.CASCADE, related_name='completions')
    completion_date = models.DateField()
    habits_completed = models.JSONField(default=list)
    completion_percentage = models.FloatField(default=0.0)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['habit_stack', 'completion_date']
    
    def __str__(self):
        return f"{self.habit_stack.name} - {self.completion_date} - {self.completion_percentage}%"

class EnvironmentSetting(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='environment_settings')
    setting_name = models.CharField(max_length=100)
    description = models.TextField()
    activity_types = models.ManyToManyField(ActivityType, blank=True)
    settings_json = models.JSONField(default=dict)  # lighting, noise, tools, etc.
    is_active = models.BooleanField(default=True)
    effectiveness_rating = models.FloatField(default=0.0)
    
    def __str__(self):
        return f"{self.user.username} - {self.setting_name}"