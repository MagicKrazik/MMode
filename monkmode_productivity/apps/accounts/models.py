from django.contrib.auth.models import AbstractUser
from django.db import models

class UserProfile(models.Model):
    """Extended user profile with Monk Mode preferences"""
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='monk_mode_profile')
    
    # Personal preferences
    timezone = models.CharField(max_length=50, default='UTC')
    preferred_wake_time = models.TimeField(null=True, blank=True)
    preferred_sleep_time = models.TimeField(null=True, blank=True)
    
    # Monk Mode settings
    default_deep_work_duration = models.IntegerField(default=120)  # minutes
    preferred_break_duration = models.IntegerField(default=15)  # minutes
    notification_preferences = models.JSONField(default=dict)
    
    # Motivation settings
    daily_motivation_enabled = models.BooleanField(default=True)
    motivation_time = models.TimeField(null=True, blank=True)
    emergency_motivation_keywords = models.JSONField(default=list)
    
    # Support network settings
    support_network_enabled = models.BooleanField(default=True)
    emergency_contact_threshold = models.IntegerField(default=2)  # mood rating threshold
    
    # Energy tracking
    energy_tracking_enabled = models.BooleanField(default=True)
    energy_reminder_frequency = models.IntegerField(default=4)  # hours
    
    # Privacy settings
    anonymous_progress_sharing = models.BooleanField(default=False)
    public_achievements = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"