from django.utils import timezone
from django.db.models import Avg, Count, Q
from apps.core.models import (
    ScheduledActivity, TaskPriorityScore, UserProductivityPattern,
    EnergyLog, MonkModeObjective, UserDailyLog
)
from datetime import datetime, timedelta
import math
import logging

logger = logging.getLogger(__name__)

class PriorityEngine:
    """
    Intelligent task prioritization engine that considers multiple factors
    to optimize user's daily focus and maximize goal achievement.
    """
    
    # Weight configuration for different priority factors
    WEIGHTS = {
        'deadline_urgency': 0.25,
        'goal_impact': 0.25,
        'energy_alignment': 0.20,
        'dependency_weight': 0.15,
        'user_preference': 0.10,
        'momentum_factor': 0.05
    }
    
    @staticmethod
    def calculate_daily_priorities(user, target_date=None):
        """Calculate priority scores for all activities on a given date"""
        if target_date is None:
            target_date = timezone.now().date()
        
        try:
            # Get user's active monk mode period
            active_period = user.monk_mode_goals.filter(
                current_status='active'
            ).first()
            
            if not active_period or not active_period.periods.filter(is_active=True).exists():
                return []
            
            period = active_period.periods.filter(is_active=True).first()
            
            # Calculate day of period
            day_of_period = (target_date - period.start_date).days + 1
            
            # Get activities for this day
            activities = ScheduledActivity.objects.filter(
                monk_mode_period=period,
                day_of_period=day_of_period
            )
            
            prioritized_activities = []
            
            for activity in activities:
                # Calculate individual factor scores
                deadline_score = PriorityEngine._calculate_deadline_urgency(activity, target_date)
                goal_impact_score = PriorityEngine._calculate_goal_impact(activity)
                energy_score = PriorityEngine._calculate_energy_alignment(activity, user, target_date)
                dependency_score = PriorityEngine._calculate_dependency_weight(activity)
                preference_score = PriorityEngine._calculate_user_preference(activity, user)
                momentum_score = PriorityEngine._calculate_momentum_factor(activity, user)
                
                # Calculate final weighted score
                final_score = (
                    deadline_score * PriorityEngine.WEIGHTS['deadline_urgency'] +
                    goal_impact_score * PriorityEngine.WEIGHTS['goal_impact'] +
                    energy_score * PriorityEngine.WEIGHTS['energy_alignment'] +
                    dependency_score * PriorityEngine.WEIGHTS['dependency_weight'] +
                    preference_score * PriorityEngine.WEIGHTS['user_preference'] +
                    momentum_score * PriorityEngine.WEIGHTS['momentum_factor']
                )
                
                # Store or update priority score
                priority_score, created = TaskPriorityScore.objects.get_or_create(
                    scheduled_activity=activity,
                    defaults={
                        'deadline_urgency': deadline_score,
                        'goal_impact': goal_impact_score,
                        'energy_requirement': energy_score,
                        'dependency_weight': dependency_score,
                        'user_preference': preference_score,
                        'momentum_factor': momentum_score,
                        'final_score': final_score
                    }
                )
                
                if not created:
                    priority_score.deadline_urgency = deadline_score
                    priority_score.goal_impact = goal_impact_score
                    priority_score.energy_requirement = energy_score
                    priority_score.dependency_weight = dependency_score
                    priority_score.user_preference = preference_score
                    priority_score.momentum_factor = momentum_score
                    priority_score.final_score = final_score
                    priority_score.save()
                
                # Update activity priority score
                activity.priority_score = final_score
                activity.save()
                
                prioritized_activities.append({
                    'activity': activity,
                    'priority_score': priority_score,
                    'final_score': final_score
                })
            
            # Sort by final score (highest first)
            prioritized_activities.sort(key=lambda x: x['final_score'], reverse=True)
            
            return prioritized_activities
            
        except Exception as e:
            logger.error(f"Error calculating daily priorities for user {user.id}: {str(e)}")
            return []
    
    @staticmethod
    def _calculate_deadline_urgency(activity, target_date):
        """Calculate urgency based on deadlines (0.0 - 1.0)"""
        try:
            # Get related objectives with deadlines
            goal = activity.monk_mode_period.goal
            objectives_with_deadlines = goal.objectives.filter(
                due_date__isnull=False,
                is_completed=False
            ).order_by('due_date')
            
            if not objectives_with_deadlines.exists():
                return 0.5  # Neutral score if no deadlines
            
            # Find the most urgent deadline
            nearest_deadline = objectives_with_deadlines.first().due_date
            days_until_deadline = (nearest_deadline - target_date).days
            
            if days_until_deadline <= 0:
                return 1.0  # Maximum urgency for overdue tasks
            elif days_until_deadline <= 1:
                return 0.9  # Very urgent (due tomorrow)
            elif days_until_deadline <= 3:
                return 0.8  # Urgent (due within 3 days)
            elif days_until_deadline <= 7:
                return 0.6  # Moderately urgent (due within a week)
            elif days_until_deadline <= 14:
                return 0.4  # Some urgency (due within 2 weeks)
            else:
                return 0.2  # Low urgency (due later)
                
        except Exception as e:
            logger.error(f"Error calculating deadline urgency: {str(e)}")
            return 0.5
    
    @staticmethod
    def _calculate_goal_impact(activity):
        """Calculate how much this activity impacts the main goal (0.0 - 1.0)"""
        try:
            # Deep work activities have highest impact
            if activity.activity_type.name.lower() in ['deep work', 'project focus', 'skill development']:
                return 1.0
            
            # Supporting activities have medium-high impact
            elif activity.activity_type.name.lower() in ['planning', 'research', 'learning']:
                return 0.8
            
            # Health and maintenance have medium impact
            elif activity.activity_type.name.lower() in ['exercise', 'mindfulness', 'reflection']:
                return 0.6
            
            # Basic needs have lower direct impact but are necessary
            elif activity.activity_type.name.lower() in ['sleep', 'cooking', 'partner time']:
                return 0.4
            
            # Everything else
            else:
                return 0.5
                
        except Exception as e:
            logger.error(f"Error calculating goal impact: {str(e)}")
            return 0.5
    
    @staticmethod
    def _calculate_energy_alignment(activity, user, target_date):
        """Calculate how well activity aligns with user's energy patterns (0.0 - 1.0)"""
        try:
            # Get user's energy prediction for this time
            predicted_energy = PriorityEngine._predict_user_energy(
                user, target_date, activity.start_time
            )
            
            # Get activity's energy requirement
            required_energy = activity.energy_required
            
            # Calculate alignment score
            if predicted_energy >= required_energy:
                # Good alignment - user has enough energy
                alignment = 1.0 - abs(predicted_energy - required_energy) / 10.0
                return max(0.6, alignment)  # Minimum 0.6 for sufficient energy
            else:
                # Poor alignment - user doesn't have enough energy
                energy_deficit = required_energy - predicted_energy
                penalty = energy_deficit / 10.0
                return max(0.1, 0.5 - penalty)  # Penalize energy mismatches
                
        except Exception as e:
            logger.error(f"Error calculating energy alignment: {str(e)}")
            return 0.5
    
    @staticmethod
    def _predict_user_energy(user, date, time):
        """Predict user's energy level at specific date/time"""
        try:
            hour = time.hour
            
            # Get historical energy data for this hour
            energy_logs = EnergyLog.objects.filter(
                user=user,
                timestamp__hour=hour,
                timestamp__gte=timezone.now() - timedelta(days=30)
            )
            
            if energy_logs.exists():
                avg_energy = energy_logs.aggregate(avg=Avg('energy_level'))['avg']
                return avg_energy
            
            # Fallback to general energy patterns if no specific data
            productivity_pattern = UserProductivityPattern.objects.filter(
                user=user,
                hour_of_day=hour
            ).aggregate(avg_energy=Avg('energy_level'))['avg_energy']
            
            if productivity_pattern:
                return productivity_pattern
            
            # Default energy pattern if no data available
            return PriorityEngine._get_default_energy_pattern(hour)
            
        except Exception as e:
            logger.error(f"Error predicting user energy: {str(e)}")
            return 5.0  # Default energy level
    
    @staticmethod
    def _get_default_energy_pattern(hour):
        """Get default energy pattern based on common circadian rhythms"""
        if 6 <= hour <= 9:
            return 7.0  # Morning energy
        elif 10 <= hour <= 12:
            return 8.5  # Peak morning
        elif 13 <= hour <= 15:
            return 6.0  # Post-lunch dip
        elif 16 <= hour <= 18:
            return 7.5  # Afternoon energy
        elif 19 <= hour <= 21:
            return 6.5  # Evening
        else:
            return 4.0  # Night/very early morning
    
    @staticmethod
    def _calculate_dependency_weight(activity):
        """Calculate weight based on task dependencies (0.0 - 1.0)"""
        try:
            # Check if this activity blocks other tasks
            goal = activity.monk_mode_period.goal
            
            # Look for objectives that might depend on this activity
            # This is a simplified version - in a more complex system,
            # you'd have explicit dependency mapping
            
            activity_description = activity.description.lower()
            
            # Activities that typically block others get higher priority
            blocking_keywords = [
                'foundation', 'setup', 'planning', 'research', 
                'design', 'architecture', 'framework'
            ]
            
            for keyword in blocking_keywords:
                if keyword in activity_description:
                    return 0.8
            
            # Activities that are typically dependent get lower priority
            dependent_keywords = [
                'polish', 'refine', 'optimize', 'review', 'test'
            ]
            
            for keyword in dependent_keywords:
                if keyword in activity_description:
                    return 0.3
            
            return 0.5  # Neutral dependency weight
            
        except Exception as e:
            logger.error(f"Error calculating dependency weight: {str(e)}")
            return 0.5
    
    @staticmethod
    def _calculate_user_preference(activity, user):
        """Calculate user preference based on historical performance (0.0 - 1.0)"""
        try:
            # Get user's historical performance with this activity type
            productivity_patterns = UserProductivityPattern.objects.filter(
                user=user,
                activity_type=activity.activity_type
            )
            
            if productivity_patterns.exists():
                avg_performance = productivity_patterns.aggregate(
                    avg=Avg('average_performance')
                )['avg']
                return min(1.0, max(0.0, avg_performance))
            
            # Check completion rates for similar activities
            similar_activities = ScheduledActivity.objects.filter(
                monk_mode_period__goal__user=user,
                activity_type=activity.activity_type,
                is_completed=True
            )
            
            total_similar = ScheduledActivity.objects.filter(
                monk_mode_period__goal__user=user,
                activity_type=activity.activity_type
            ).count()
            
            if total_similar > 0:
                completion_rate = similar_activities.count() / total_similar
                return completion_rate
            
            return 0.5  # Neutral preference if no history
            
        except Exception as e:
            logger.error(f"Error calculating user preference: {str(e)}")
            return 0.5
    
    @staticmethod
    def _calculate_momentum_factor(activity, user):
        """Calculate momentum bonus for continuing similar work (0.0 - 1.0)"""
        try:
            # Check recent activity completions
            recent_activities = ScheduledActivity.objects.filter(
                monk_mode_period__goal__user=user,
                completed_at__gte=timezone.now() - timedelta(days=2),
                is_completed=True
            ).order_by('-completed_at')
            
            if not recent_activities.exists():
                return 0.5
            
            # Check for similar activity types in recent completions
            same_type_recent = recent_activities.filter(
                activity_type=activity.activity_type
            ).count()
            
            if same_type_recent > 0:
                # Bonus for continuing similar work
                momentum_bonus = min(0.3, same_type_recent * 0.1)
                return 0.5 + momentum_bonus
            
            # Check for complementary activities
            complementary_types = PriorityEngine._get_complementary_activities(
                activity.activity_type.name
            )
            
            complementary_recent = recent_activities.filter(
                activity_type__name__in=complementary_types
            ).count()
            
            if complementary_recent > 0:
                return 0.6  # Small bonus for complementary momentum
            
            return 0.4  # Slight penalty for context switching
            
        except Exception as e:
            logger.error(f"Error calculating momentum factor: {str(e)}")
            return 0.5
    
    @staticmethod
    def _get_complementary_activities(activity_name):
        """Get list of activities that complement the given activity"""
        complementary_map = {
            'Deep Work': ['Planning', 'Research', 'Learning'],
            'Exercise': ['Mindfulness', 'Sleep', 'Cooking'],
            'Learning': ['Deep Work', 'Reflection', 'Practice'],
            'Planning': ['Deep Work', 'Research'],
            'Research': ['Deep Work', 'Planning', 'Learning'],
            'Mindfulness': ['Exercise', 'Reflection', 'Sleep'],
            'Reflection': ['Mindfulness', 'Planning', 'Learning']
        }
        
        return complementary_map.get(activity_name, [])
    
    @staticmethod
    def get_focus_recommendations(user, target_date=None):
        """Get intelligent focus recommendations for the user"""
        try:
            prioritized_activities = PriorityEngine.calculate_daily_priorities(user, target_date)
            
            if not prioritized_activities:
                return {
                    'primary_focus': None,
                    'secondary_focus': [],
                    'recommendations': ['No active Monk Mode period found.']
                }
            
            # Get top 3 activities
            top_activities = prioritized_activities[:3]
            primary_focus = top_activities[0] if top_activities else None
            secondary_focus = top_activities[1:3] if len(top_activities) > 1 else []
            
            # Generate recommendations
            recommendations = PriorityEngine._generate_focus_recommendations(
                user, prioritized_activities, target_date
            )
            
            return {
                'primary_focus': primary_focus,
                'secondary_focus': secondary_focus,
                'all_activities': prioritized_activities,
                'recommendations': recommendations,
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"Error getting focus recommendations: {str(e)}")
            return {
                'primary_focus': None,
                'secondary_focus': [],
                'recommendations': ['Error generating recommendations.']
            }
    
    @staticmethod
    def _generate_focus_recommendations(user, prioritized_activities, target_date):
        """Generate personalized focus recommendations"""
        recommendations = []
        
        if not prioritized_activities:
            return ['No activities scheduled for today.']
        
        # Analyze the priority distribution
        scores = [item['final_score'] for item in prioritized_activities]
        avg_score = sum(scores) / len(scores)
        
        # Primary recommendation based on top activity
        top_activity = prioritized_activities[0]['activity']
        recommendations.append(
            f"🎯 Focus on '{top_activity.description}' first - it has the highest impact on your goals."
        )
        
        # Energy-based recommendations
        predicted_energy = PriorityEngine._predict_user_energy(
            user, target_date or timezone.now().date(), timezone.now().time()
        )
        
        if predicted_energy >= 7:
            recommendations.append(
                f"⚡ Your energy is high ({predicted_energy:.1f}/10) - perfect time for demanding tasks!"
            )
        elif predicted_energy <= 4:
            recommendations.append(
                f"🔋 Energy is low ({predicted_energy:.1f}/10) - consider lighter tasks or take a break."
            )
        
        # Time-based recommendations
        current_hour = timezone.now().hour
        if 6 <= current_hour <= 10:
            recommendations.append(
                "🌅 Morning is great for deep work - tackle your most important tasks now."
            )
        elif 14 <= current_hour <= 16:
            recommendations.append(
                "🕐 Post-lunch period - consider lighter or creative tasks."
            )
        
        # Deadline pressure recommendations
        urgent_activities = [
            item for item in prioritized_activities 
            if item['priority_score'].deadline_urgency > 0.7
        ]
        
        if urgent_activities:
            recommendations.append(
                f"⏰ You have {len(urgent_activities)} urgent task(s) - prioritize time-sensitive work."
            )
        
        # Momentum recommendations
        high_momentum = [
            item for item in prioritized_activities 
            if item['priority_score'].momentum_factor > 0.6
        ]
        
        if high_momentum:
            recommendations.append(
                "🚀 You're on a roll with similar tasks - keep the momentum going!"
            )
        
        return recommendations
    
    @staticmethod
    def update_productivity_patterns(user):
        """Update user's productivity patterns based on completed activities"""
        try:
            # Get completed activities from the last 30 days
            completed_activities = ScheduledActivity.objects.filter(
                monk_mode_period__goal__user=user,
                is_completed=True,
                completed_at__gte=timezone.now() - timedelta(days=30)
            )
            
            patterns_updated = 0
            
            for activity in completed_activities:
                if not activity.completed_at:
                    continue
                
                hour = activity.completed_at.hour
                activity_type = activity.activity_type
                
                # Calculate performance score based on completion quality and timing
                performance_score = PriorityEngine._calculate_performance_score(activity)
                
                # Get or create productivity pattern
                pattern, created = UserProductivityPattern.objects.get_or_create(
                    user=user,
                    hour_of_day=hour,
                    activity_type=activity_type,
                    defaults={
                        'average_performance': performance_score,
                        'energy_level': activity.energy_required,
                        'completion_rate': 1.0,
                        'sample_size': 1
                    }
                )
                
                if not created:
                    # Update existing pattern using weighted average
                    total_samples = pattern.sample_size + 1
                    pattern.average_performance = (
                        (pattern.average_performance * pattern.sample_size + performance_score) / total_samples
                    )
                    pattern.sample_size = total_samples
                    pattern.save()
                
                patterns_updated += 1
            
            logger.info(f"Updated {patterns_updated} productivity patterns for user {user.id}")
            return patterns_updated
            
        except Exception as e:
            logger.error(f"Error updating productivity patterns: {str(e)}")
            return 0
    
    @staticmethod
    def _calculate_performance_score(activity):
        """Calculate performance score for a completed activity"""
        try:
            score = 0.5  # Base score
            
            # Quality bonus
            if activity.completion_quality:
                score += (activity.completion_quality - 3) * 0.1  # -0.2 to +0.2
            
            # Timing bonus/penalty
            if activity.actual_start_time and activity.actual_end_time:
                scheduled_duration = activity.duration_minutes
                actual_duration = activity.actual_duration_minutes
                
                if actual_duration and scheduled_duration:
                    timing_ratio = actual_duration / scheduled_duration
                    if 0.8 <= timing_ratio <= 1.2:  # Within 20% of scheduled time
                        score += 0.2
                    elif timing_ratio > 1.5:  # Took much longer than expected
                        score -= 0.2
            
            return max(0.0, min(1.0, score))
            
        except Exception as e:
            logger.error(f"Error calculating performance score: {str(e)}")
            return 0.5