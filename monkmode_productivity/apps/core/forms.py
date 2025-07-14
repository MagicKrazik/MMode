from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import MonkModeGoal, MonkModeObjective, UserDailyLog

class MonkModeGoalForm(forms.ModelForm):
    class Meta:
        model = MonkModeGoal
        fields = ['title', 'description', 'start_date', 'end_date', 'target_outcome']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'target_outcome': forms.Textarea(attrs={'rows': 3}),
        }

class MonkModeObjectiveForm(forms.ModelForm):
    class Meta:
        model = MonkModeObjective
        fields = ['description', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class UserDailyLogForm(forms.ModelForm):
    class Meta:
        model = UserDailyLog
        fields = ['reflection_text', 'adherence_score', 'mood_rating']
        widgets = {
            'reflection_text': forms.Textarea(attrs={'rows': 4, 'placeholder': 'How did your day go? What challenges did you face?'}),
            'adherence_score': forms.Select(attrs={'class': 'form-control'}),
            'mood_rating': forms.Select(attrs={'class': 'form-control'}),
        }
