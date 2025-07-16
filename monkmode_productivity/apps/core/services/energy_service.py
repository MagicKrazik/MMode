from django.utils import timezone
from django.db.models import Avg, Count, Q
from apps.core.models import EnergyLog, EnergyPrediction, UserDailyLog, ScheduledActivity
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class EnergyManagementService:
    """
    Service for tracking, analyzing, and predicting user energy levels
    to optimize task scheduling and prevent burnout.
    """
    
    @staticmethod
    def log_energy_level(user, energy_level, context_factors=None, notes=""):
        """Log user's current energy level with enhanced validation"""
        try:
            if context_factors is None:
                context_factors = {}
            
            # Validate energy level
            energy_level = int(energy_level) if energy_level else 5
            energy_level = max(1, min(10, energy_level))
            
            # Get the most recent activity if not provided in context
            if 'activity_before' not in context_factors:
                try:
                    recent_activity = ScheduledActivity.objects.filter(
                        monk_mode_period__goal__user=user,
                        actual_end_time__lte=timezone.now(),
                        actual_end_time__gte=timezone.now() - timedelta(hours=2)
                    ).order_by('-actual_end_time').first()
                    
                    if recent_activity:
                        context_factors['activity_before'] = recent_activity.activity_type.name
                except Exception as e:
                    logger.warning(f"Error getting recent activity: {str(e)}")
            
            # Clean and validate context factors
            validated_context = {}
            for key, value in context_factors.items():
                if value is not None:
                    # Convert numeric strings to proper types
                    if isinstance(value, str) and value.isdigit():
                        validated_context[key] = int(value)
                    elif isinstance(value, str):
                        validated_context[key] = str(value).strip()
                    else:
                        validated_context[key] = value
            
            energy_log = EnergyLog.objects.create(
                user=user,
                timestamp=timezone.now(),
                energy_level=energy_level,
                context_factors=validated_context,
                notes=notes or ""
            )
            
            # Update daily log if exists
            today = timezone.now().date()
            daily_log, created = UserDailyLog.objects.get_or_create(
                user=user,
                log_date=today,
                defaults={}
            )
            
            # Update energy level based on time of day
            current_hour = timezone.now().hour
            if 5 <= current_hour <= 11:
                daily_log.energy_level_morning = energy_level
            elif 12 <= current_hour <= 17:
                daily_log.energy_level_afternoon = energy_level
            elif 18 <= current_hour <= 23:
                daily_log.energy_level_evening = energy_level
            
            daily_log.save()
            
            # Trigger energy-based recommendations
            EnergyManagementService._check_energy_alerts(user, energy_level)
            
            return energy_log
            
        except Exception as e:
            logger.error(f"Error logging energy level for user {user.id}: {str(e)}")
            return None
    
    @staticmethod
    def _check_energy_alerts(user, energy_level):
        """Check if energy level warrants alerts or recommendations"""
        try:
            # Validate energy level is numeric
            if not isinstance(energy_level, (int, float)):
                logger.warning(f"Invalid energy level type: {type(energy_level)}")
                return
            
            energy_level = float(energy_level)
            
            # Get recent energy levels
            recent_logs = EnergyLog.objects.filter(
                user=user,
                timestamp__gte=timezone.now() - timedelta(hours=6)
            ).order_by('-timestamp')[:3]
            
            if len(recent_logs) >= 2:
                energy_trend = [float(log.energy_level) for log in recent_logs]
                avg_recent = sum(energy_trend) / len(energy_trend)
                
                # Check for concerning patterns
                if energy_level <= 3 and avg_recent <= 4:
                    EnergyManagementService._trigger_low_energy_protocol(user, energy_level)
                elif energy_level >= 8 and avg_recent >= 7:
                    EnergyManagementService._suggest_high_energy_tasks(user, energy_level)
            
        except Exception as e:
            logger.error(f"Error checking energy alerts: {str(e)}")
    
    @staticmethod
    def _trigger_low_energy_protocol(user, energy_level):
        """Trigger protocol for low energy levels"""
        try:
            recommendations = [
                "🔋 Your energy is running low. Consider taking a short break.",
                "💧 Stay hydrated - dehydration can impact energy levels.",
                "🚶‍♂️ A 5-minute walk might help boost your energy.",
                "🧘‍♀️ Try a brief mindfulness exercise to recharge."
            ]
            
            # Check if it's time for a scheduled break
            current_time = timezone.now().time()
            
            try:
                upcoming_activities = ScheduledActivity.objects.filter(
                    monk_mode_period__goal__user=user,
                    start_time__gte=current_time,
                    start_time__lte=(timezone.now() + timedelta(hours=2)).time(),
                    activity_type__name__icontains='break'
                )
                
                if not upcoming_activities.exists():
                    recommendations.append("📅 Consider scheduling a break in your next hour.")
            except Exception as e:
                logger.warning(f"Error checking upcoming activities: {str(e)}")
            
            # Store recommendations in user's daily log
            today = timezone.now().date()
            daily_log, _ = UserDailyLog.objects.get_or_create(
                user=user,
                log_date=today,
                defaults={}
            )
            
            current_challenges = daily_log.challenges_faced or ""
            energy_note = f"\n[{timezone.now().strftime('%H:%M')}] Low energy alert (level: {energy_level})"
            daily_log.challenges_faced = current_challenges + energy_note
            daily_log.save()
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error triggering low energy protocol: {str(e)}")
            return []
    
    @staticmethod
    def _suggest_high_energy_tasks(user, energy_level):
        """Suggest high-impact tasks when energy is high"""
        try:
            # Get current day's remaining activities
            current_time = timezone.now().time()
            
            try:
                remaining_activities = ScheduledActivity.objects.filter(
                    monk_mode_period__goal__user=user,
                    start_time__gte=current_time,
                    is_completed=False,
                    energy_required__gte=6  # High energy tasks
                ).order_by('start_time')[:3]
                
                suggestions = []
                if remaining_activities.exists():
                    suggestions.append(f"⚡ High energy detected! Perfect time for:")
                    for activity in remaining_activities:
                        suggestions.append(f"  • {activity.description}")
                else:
                    suggestions.append("⚡ High energy! Consider tackling challenging tasks now.")
                
                return suggestions
            except Exception as e:
                logger.warning(f"Error getting remaining activities: {str(e)}")
                return ["⚡ High energy! Consider tackling challenging tasks now."]
            
        except Exception as e:
            logger.error(f"Error suggesting high energy tasks: {str(e)}")
            return []
    
    @staticmethod
    def predict_energy_levels(user, prediction_date=None, hours_ahead=24):
        """Predict user's energy levels for upcoming hours"""
        try:
            if prediction_date is None:
                prediction_date = timezone.now().date()
            
            # Get historical energy data
            historical_data = EnergyLog.objects.filter(
                user=user,
                timestamp__gte=timezone.now() - timedelta(days=30)
            ).order_by('timestamp')
            
            if not historical_data.exists():
                return EnergyManagementService._generate_default_predictions(
                    user, prediction_date, hours_ahead
                )
            
            predictions = []
            current_datetime = timezone.now().replace(
                year=prediction_date.year,
                month=prediction_date.month,
                day=prediction_date.day,
                minute=0,
                second=0,
                microsecond=0
            )
            
            for hour_offset in range(hours_ahead):
                prediction_time = current_datetime + timedelta(hours=hour_offset)
                
                # Get historical data for this hour of day
                hour_data = historical_data.filter(
                    timestamp__hour=prediction_time.hour
                )
                
                if hour_data.exists():
                    # Calculate weighted average based on recency
                    energy_values = []
                    weights = []
                    
                    for log in hour_data:
                        days_ago = (timezone.now().date() - log.timestamp.date()).days
                        weight = 1.0 / (1.0 + days_ago * 0.1)  # More recent = higher weight
                        energy_values.append(float(log.energy_level))
                        weights.append(weight)
                    
                    # Calculate weighted average
                    total_weight = sum(weights)
                    if total_weight > 0:
                        predicted_energy = sum(e * w for e, w in zip(energy_values, weights)) / total_weight
                    else:
                        predicted_energy = sum(energy_values) / len(energy_values)
                    
                    confidence = min(0.95, len(hour_data) * 0.1)  # Higher confidence with more data
                else:
                    # Use default pattern if no historical data for this hour
                    predicted_energy = EnergyManagementService._get_default_energy_for_hour(
                        prediction_time.hour
                    )
                    confidence = 0.3  # Low confidence for default predictions
                
                # Adjust based on context factors
                predicted_energy = EnergyManagementService._adjust_for_context(
                    user, predicted_energy, prediction_time
                )
                
                # Create prediction record
                prediction = EnergyPrediction.objects.create(
                    user=user,
                    predicted_for=prediction_time,
                    predicted_energy=predicted_energy,
                    confidence_score=confidence
                )
                
                predictions.append(prediction)
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting energy levels: {str(e)}")
            return []
    
    @staticmethod
    def _generate_default_predictions(user, prediction_date, hours_ahead):
        """Generate default energy predictions for new users"""
        predictions = []
        current_datetime = timezone.now().replace(
            year=prediction_date.year,
            month=prediction_date.month,
            day=prediction_date.day,
            minute=0,
            second=0,
            microsecond=0
        )
        
        for hour_offset in range(hours_ahead):
            prediction_time = current_datetime + timedelta(hours=hour_offset)
            predicted_energy = EnergyManagementService._get_default_energy_for_hour(
                prediction_time.hour
            )
            
            prediction = EnergyPrediction.objects.create(
                user=user,
                predicted_for=prediction_time,
                predicted_energy=predicted_energy,
                confidence_score=0.4  # Moderate confidence for defaults
            )
            
            predictions.append(prediction)
        
        return predictions
    
    @staticmethod
    def _get_default_energy_for_hour(hour):
        """Get default energy level based on typical circadian rhythms"""
        # Based on common energy patterns
        energy_map = {
            0: 3, 1: 2, 2: 2, 3: 2, 4: 2, 5: 3,  # Night/early morning
            6: 5, 7: 6, 8: 7, 9: 8, 10: 8, 11: 8,  # Morning peak
            12: 7, 13: 6, 14: 5, 15: 5, 16: 6,     # Afternoon dip
            17: 7, 18: 7, 19: 6, 20: 5, 21: 4,     # Evening
            22: 4, 23: 3                            # Pre-sleep
        }
        return energy_map.get(hour, 5)
    
    @staticmethod
    def _adjust_for_context(user, base_energy, prediction_time):
        """Adjust energy prediction based on context factors"""
        try:
            adjusted_energy = float(base_energy)
            
            # Check for scheduled activities that might affect energy
            try:
                scheduled_activities = ScheduledActivity.objects.filter(
                    monk_mode_period__goal__user=user,
                    start_time__lte=prediction_time.time(),
                    end_time__gte=(prediction_time - timedelta(hours=2)).time()
                )
                
                for activity in scheduled_activities:
                    # Exercise typically boosts energy for a few hours
                    if 'exercise' in activity.activity_type.name.lower():
                        adjusted_energy += 1.0
                    
                    # Deep work can be draining
                    elif 'deep work' in activity.activity_type.name.lower():
                        adjusted_energy -= 0.5
                    
                    # Rest activities restore energy
                    elif activity.activity_type.name.lower() in ['break', 'mindfulness', 'meditation']:
                        adjusted_energy += 0.5
            except Exception as e:
                logger.warning(f"Error adjusting for scheduled activities: {str(e)}")
            
            # Weekend vs weekday adjustment
            if prediction_time.weekday() >= 5:  # Weekend
                adjusted_energy += 0.5  # Generally higher energy on weekends
            
            # Time-based adjustments
            if prediction_time.hour in [14, 15]:  # Post-lunch dip
                adjusted_energy -= 0.5
            elif prediction_time.hour in [10, 11]:  # Morning peak
                adjusted_energy += 0.5
            
            return max(1.0, min(10.0, adjusted_energy))
            
        except Exception as e:
            logger.error(f"Error adjusting energy for context: {str(e)}")
            return float(base_energy)
    
    @staticmethod
    def get_energy_insights(user, days_back=30):
        """Get comprehensive energy insights for the user"""
        try:
            # Get energy logs from the specified period
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days_back)
            
            energy_logs = EnergyLog.objects.filter(
                user=user,
                timestamp__gte=start_date
            ).order_by('timestamp')
            
            if not energy_logs.exists():
                return {
                    'message': 'Not enough energy data available. Start logging your energy levels!',
                    'recommendations': [
                        'Log your energy levels 3-4 times per day',
                        'Note what activities or factors affect your energy',
                        'Track patterns over at least a week for insights'
                    ]
                }
            
            # Calculate basic statistics with type validation
            energy_values = []
            for log in energy_logs:
                try:
                    energy_values.append(float(log.energy_level))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid energy level in log {log.id}: {log.energy_level}")
                    continue
            
            if not energy_values:
                return {'error': 'No valid energy data found'}
            
            avg_energy = sum(energy_values) / len(energy_values)
            min_energy = min(energy_values)
            max_energy = max(energy_values)
            
            # Find peak energy hours
            hourly_energy = {}
            for log in energy_logs:
                try:
                    hour = log.timestamp.hour
                    energy_val = float(log.energy_level)
                    if hour not in hourly_energy:
                        hourly_energy[hour] = []
                    hourly_energy[hour].append(energy_val)
                except (ValueError, TypeError):
                    continue
            
            hourly_averages = {
                hour: sum(values) / len(values) 
                for hour, values in hourly_energy.items()
                if values  # Only include hours with valid data
            }
            
            if hourly_averages:
                peak_hours = sorted(hourly_averages.items(), key=lambda x: x[1], reverse=True)[:3]
                low_hours = sorted(hourly_averages.items(), key=lambda x: x[1])[:3]
            else:
                peak_hours = []
                low_hours = []
            
            # Analyze energy patterns by day of week
            daily_energy = {}
            for log in energy_logs:
                try:
                    day = log.timestamp.strftime('%A')
                    energy_val = float(log.energy_level)
                    if day not in daily_energy:
                        daily_energy[day] = []
                    daily_energy[day].append(energy_val)
                except (ValueError, TypeError):
                    continue
            
            daily_averages = {
                day: sum(values) / len(values) 
                for day, values in daily_energy.items()
                if values
            }
            
            # Find energy drains and boosters
            context_analysis = EnergyManagementService._analyze_context_factors(energy_logs)
            
            # Generate recommendations
            recommendations = EnergyManagementService._generate_energy_recommendations(
                hourly_averages, daily_averages, context_analysis, avg_energy
            )
            
            return {
                'summary': {
                    'average_energy': round(avg_energy, 1),
                    'energy_range': f"{min_energy} - {max_energy}",
                    'total_logs': len(energy_logs),
                    'days_tracked': days_back
                },
                'peak_hours': [f"{hour:02d}:00 ({avg:.1f}/10)" for hour, avg in peak_hours],
                'low_hours': [f"{hour:02d}:00 ({avg:.1f}/10)" for hour, avg in low_hours],
                'daily_patterns': daily_averages,
                'energy_boosters': context_analysis['boosters'],
                'energy_drains': context_analysis['drains'],
                'recommendations': recommendations,
                'trends': EnergyManagementService._calculate_energy_trends(energy_logs)
            }
            
        except Exception as e:
            logger.error(f"Error getting energy insights: {str(e)}")
            return {'error': 'Unable to generate energy insights'}
    
    @staticmethod
    def _analyze_context_factors(energy_logs):
        """Analyze context factors that affect energy"""
        try:
            boosters = {}
            drains = {}
            
            for log in energy_logs:
                try:
                    energy_level = float(log.energy_level)
                    factors = log.context_factors or {}
                    
                    # Analyze activities before energy logging
                    if 'activity_before' in factors:
                        activity = str(factors['activity_before'])
                        
                        if energy_level >= 7:
                            boosters[activity] = boosters.get(activity, 0) + 1
                        elif energy_level <= 4:
                            drains[activity] = drains.get(activity, 0) + 1
                    
                    # Analyze other context factors
                    for factor, value in factors.items():
                        if factor != 'activity_before' and value is not None:
                            factor_str = f"{factor}: {str(value)}"
                            if energy_level >= 7:
                                boosters[factor_str] = boosters.get(factor_str, 0) + 1
                            elif energy_level <= 4:
                                drains[factor_str] = drains.get(factor_str, 0) + 1
                                
                except (ValueError, TypeError):
                    continue
            
            # Sort by frequency
            top_boosters = sorted(boosters.items(), key=lambda x: x[1], reverse=True)[:5]
            top_drains = sorted(drains.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                'boosters': [f"{factor} ({count}x)" for factor, count in top_boosters],
                'drains': [f"{factor} ({count}x)" for factor, count in top_drains]
            }
            
        except Exception as e:
            logger.error(f"Error analyzing context factors: {str(e)}")
            return {'boosters': [], 'drains': []}
    
    @staticmethod
    def _generate_energy_recommendations(hourly_avg, daily_avg, context_analysis, avg_energy):
        """Generate personalized energy management recommendations"""
        recommendations = []
        
        try:
            # Peak hour recommendations
            if hourly_avg:
                peak_hour = max(hourly_avg.items(), key=lambda x: x[1])
                recommendations.append(
                    f"🌟 Schedule your most important work around {peak_hour[0]:02d}:00 "
                    f"when your energy peaks at {peak_hour[1]:.1f}/10"
                )
                
                low_hour = min(hourly_avg.items(), key=lambda x: x[1])
                recommendations.append(
                    f"⏰ Avoid demanding tasks around {low_hour[0]:02d}:00 "
                    f"when energy drops to {low_hour[1]:.1f}/10"
                )
            
            # Daily pattern recommendations
            if daily_avg:
                best_day = max(daily_avg.items(), key=lambda x: x[1])
                worst_day = min(daily_avg.items(), key=lambda x: x[1])
                
                recommendations.append(
                    f"📅 {best_day[0]}s are your best days (avg: {best_day[1]:.1f}/10) - "
                    "plan important activities then"
                )
                
                if worst_day[1] < avg_energy - 1:
                    recommendations.append(
                        f"🛡️ {worst_day[0]}s tend to be challenging (avg: {worst_day[1]:.1f}/10) - "
                        "schedule lighter tasks or self-care"
                    )
            
            # Context-based recommendations
            if context_analysis['boosters']:
                top_booster = context_analysis['boosters'][0].split(' (')[0]
                recommendations.append(f"💪 '{top_booster}' consistently boosts your energy - do more of this!")
            
            if context_analysis['drains']:
                top_drain = context_analysis['drains'][0].split(' (')[0]
                recommendations.append(f"⚠️ '{top_drain}' often drains your energy - consider modifications or breaks")
            
            # General energy level recommendations
            if avg_energy < 5:
                recommendations.extend([
                    "🔋 Your average energy is low - prioritize sleep, nutrition, and stress management",
                    "🏃‍♂️ Regular exercise might help boost overall energy levels",
                    "🧘‍♀️ Consider adding more recovery activities to your schedule"
                ])
            elif avg_energy > 7:
                recommendations.extend([
                    "⚡ Great energy levels! You can handle more challenging tasks",
                    "🎯 Consider setting more ambitious goals for your Monk Mode periods"
                ])
        except Exception as e:
            logger.error(f"Error generating energy recommendations: {str(e)}")
            recommendations.append("Continue tracking your energy patterns for personalized insights")
        
        return recommendations
    
    @staticmethod
    def _calculate_energy_trends(energy_logs):
        """Calculate energy trends over time"""
        try:
            if len(energy_logs) < 7:
                return "Not enough data for trend analysis"
            
            # Split logs into two halves for comparison
            mid_point = len(energy_logs) // 2
            first_half = energy_logs[:mid_point]
            second_half = energy_logs[mid_point:]
            
            # Calculate averages with type validation
            first_values = []
            second_values = []
            
            for log in first_half:
                try:
                    first_values.append(float(log.energy_level))
                except (ValueError, TypeError):
                    continue
            
            for log in second_half:
                try:
                    second_values.append(float(log.energy_level))
                except (ValueError, TypeError):
                    continue
            
            if not first_values or not second_values:
                return "Insufficient valid data for trend analysis"
            
            first_avg = sum(first_values) / len(first_values)
            second_avg = sum(second_values) / len(second_values)
            
            difference = second_avg - first_avg
            
            if difference > 0.5:
                return f"📈 Trending up! Energy increased by {difference:.1f} points"
            elif difference < -0.5:
                return f"📉 Trending down. Energy decreased by {abs(difference):.1f} points"
            else:
                return "📊 Stable energy levels over time"
                
        except Exception as e:
            logger.error(f"Error calculating energy trends: {str(e)}")
            return "Unable to calculate trends"
    
    @staticmethod
    def get_recovery_recommendations(user):
        """Get personalized recovery recommendations with enhanced validation"""
        try:
            # Get recent energy levels
            recent_logs = EnergyLog.objects.filter(
                user=user,
                timestamp__gte=timezone.now() - timedelta(days=3)
            ).order_by('-timestamp')
            
            if not recent_logs.exists():
                return ["Start tracking your energy levels to get personalized recovery recommendations"]
            
            # Validate and calculate recent energy
            recent_energy = []
            for log in recent_logs[:5]:
                try:
                    energy_val = float(log.energy_level)
                    if 1 <= energy_val <= 10:  # Validate range
                        recent_energy.append(energy_val)
                except (ValueError, TypeError):
                    continue
            
            if not recent_energy:
                return ["Invalid energy data found. Please ensure you're logging valid energy levels (1-10)"]
            
            avg_recent = sum(recent_energy) / len(recent_energy)
            
            recommendations = []
            
            if avg_recent <= 4:
                recommendations.extend([
                    "🛌 Priority: Get 7-9 hours of quality sleep tonight",
                    "💧 Increase water intake - dehydration affects energy",
                    "🥗 Focus on nutritious meals with complex carbs and protein",
                    "🚶‍♂️ Take a 10-minute walk in natural light",
                    "📱 Reduce screen time 1 hour before bed"
                ])
            elif avg_recent <= 6:
                recommendations.extend([
                    "⏸️ Schedule 15-minute breaks between demanding tasks",
                    "🧘‍♀️ Try a 5-minute breathing exercise",
                    "🎵 Listen to energizing music during breaks",
                    "☀️ Get some sunlight exposure if possible"
                ])
            else:
                recommendations.extend([
                    "💪 You're doing great! Maintain current energy habits",
                    "🎯 Consider taking on additional challenges",
                    "📈 Your energy management is on track"
                ])
            
            # Add context-specific recommendations
            if recent_logs.exists():
                last_log = recent_logs.first()
                if last_log and last_log.context_factors:
                    factors = last_log.context_factors
                    
                    # Validate stress level
                    stress_level = factors.get('stress_level', 0)
                    try:
                        stress_level = int(stress_level) if stress_level else 0
                        if stress_level > 3:
                            recommendations.append("🧘‍♀️ High stress detected - prioritize stress management techniques")
                    except (ValueError, TypeError):
                        pass
                    
                    # Validate sleep hours
                    sleep_hours = factors.get('sleep_hours', 8)
                    try:
                        sleep_hours = float(sleep_hours) if sleep_hours else 8
                        if sleep_hours < 6:
                            recommendations.append("😴 Insufficient sleep detected - aim for 7-9 hours tonight")
                    except (ValueError, TypeError):
                        pass
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting recovery recommendations: {str(e)}")
            return ["Unable to generate recovery recommendations"]