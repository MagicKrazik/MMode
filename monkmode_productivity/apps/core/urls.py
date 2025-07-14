from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('goals/', views.goal_list, name='goal_list'),
    path('goals/create/', views.goal_create, name='goal_create'),
    path('goals/<int:goal_id>/', views.goal_detail, name='goal_detail'),
    path('goals/<int:goal_id>/edit/', views.goal_edit, name='goal_edit'),
    path('goals/<int:goal_id>/generate-schedule/', views.generate_schedule, name='generate_schedule'),
    path('schedule/<int:period_id>/', views.schedule_view, name='schedule_view'),
    path('daily-log/', views.daily_log, name='daily_log'),
    path('activity/<int:activity_id>/complete/', views.mark_activity_complete, name='mark_complete'),
]
