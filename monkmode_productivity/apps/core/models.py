from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta

class MonkModeGoal(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    target_outcome = models.TextField()
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username}"

    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    @property
    def is_active_period(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

class MonkModeObjective(models.Model):
    goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE, related_name='objectives')
    description = models.TextField()
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.goal.title} - {self.description[:50]}"

class ActivityType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    default_duration_minutes = models.IntegerField(default=60)
    is_core_monk_mode = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class MonkModePeriod(models.Model):
    goal = models.ForeignKey(MonkModeGoal, on_delete=models.CASCADE, related_name='periods')
    period_name = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.period_name} - {self.goal.title}"

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day_of_period', 'start_time']

    def __str__(self):
        return f"Day {self.day_of_period} - {self.activity_type.name}"

    @property
    def scheduled_date(self):
        return self.monk_mode_period.start_date + timedelta(days=self.day_of_period - 1)

class UserDailyLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    log_date = models.DateField()
    monk_mode_period = models.ForeignKey(MonkModePeriod, on_delete=models.CASCADE, null=True, blank=True)
    reflection_text = models.TextField()
    adherence_score = models.IntegerField(null=True, blank=True, choices=[(i, i) for i in range(1, 11)])
    mood_rating = models.IntegerField(null=True, blank=True, choices=[(i, i) for i in range(1, 6)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'log_date']
        ordering = ['-log_date']

    def __str__(self):
        return f"{self.user.username} - {self.log_date}"
