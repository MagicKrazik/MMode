from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Goal management
    path('goals/', views.goals_list, name='goals_list'),
    path('goals/create/', views.create_goal, name='create_goal'),
    path('goals/<int:goal_id>/', views.goal_detail, name='goal_detail'),
    
    # AI and planning
    path('ai-chat/', views.ai_chat, name='ai_chat'),
    path('ai-chat/<int:goal_id>/', views.ai_chat, name='ai_chat_with_goal'),
    
    # Schedule and activities
    path('schedule/<int:period_id>/', views.schedule_view, name='schedule_view'),
    path('activities/<int:activity_id>/complete/', views.complete_activity, name='complete_activity'),
    
    # Daily logging
    path('log/', views.daily_log, name='daily_log'),
    path('log/<str:date>/', views.daily_log, name='daily_log_date'),
    
    # Support network
    path('support/', views.support_network, name='support_network'),
    path('emergency-support/', views.emergency_support, name='emergency_support'),
    
    # Motivation center
    path('motivation/', views.motivation_center, name='motivation_center'),
    
    # Priority and focus
    path('priority/', views.priority_focus, name='priority_focus'),
    
    # Energy tracking
    path('energy/', views.energy_tracking, name='energy_tracking'),
    
    # Analytics
    path('analytics/', views.progress_analytics, name='progress_analytics'),
    
    # API endpoints
    path('api/energy-log/', views.api_energy_log, name='api_energy_log'),
    path('api/activities/<int:activity_id>/quick-complete/', views.api_quick_complete, name='api_quick_complete'),
]