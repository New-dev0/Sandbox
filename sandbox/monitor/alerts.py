import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sandbox.config import settings

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self):
        self.alerts = {}  # container_id -> last_alert_time
        self.alert_cooldown = 300  # 5 minutes between alerts
        
    def check_container_stats(self, container_id: str, stats: Dict[str, Any]) -> Optional[str]:
        """Check container stats and return alert message if thresholds exceeded"""
        now = datetime.now()
        last_alert = self.alerts.get(container_id)
        
        # Check alert cooldown
        if last_alert and (now - last_alert).total_seconds() < self.alert_cooldown:
            return None
            
        alert_messages = []
        
        # CPU threshold
        if stats["cpu_percent"] > settings.MONITOR_CPU_THRESHOLD:
            alert_messages.append(
                f"CPU usage at {stats['cpu_percent']:.1f}% (threshold: {settings.MONITOR_CPU_THRESHOLD}%)"
            )
            
        # Memory threshold
        memory_percent = (stats["memory_usage"] / stats["memory_limit"]) * 100
        if memory_percent > settings.MONITOR_MEMORY_THRESHOLD:
            alert_messages.append(
                f"Memory usage at {memory_percent:.1f}% (threshold: {settings.MONITOR_MEMORY_THRESHOLD}%)"
            )
            
        # Disk threshold (if available)
        if "disk_usage" in stats and stats["disk_usage"] > settings.MONITOR_DISK_THRESHOLD:
            alert_messages.append(
                f"Disk usage at {stats['disk_usage']:.1f}% (threshold: {settings.MONITOR_DISK_THRESHOLD}%)"
            )
            
        if alert_messages:
            self.alerts[container_id] = now
            return f"Container {container_id} resource alert: " + ", ".join(alert_messages)
            
        return None
        
    def check_system_stats(self, stats: Dict[str, float]) -> Optional[str]:
        """Check system stats and return alert message if thresholds exceeded"""
        now = datetime.now()
        last_alert = self.alerts.get("system")
        
        # Check alert cooldown
        if last_alert and (now - last_alert).total_seconds() < self.alert_cooldown:
            return None
            
        alert_messages = []
        
        # CPU threshold
        if stats["cpu"] > settings.MONITOR_CPU_THRESHOLD:
            alert_messages.append(
                f"System CPU at {stats['cpu']:.1f}% (threshold: {settings.MONITOR_CPU_THRESHOLD}%)"
            )
            
        # Memory threshold
        if stats["memory"] > settings.MONITOR_MEMORY_THRESHOLD:
            alert_messages.append(
                f"System memory at {stats['memory']:.1f}% (threshold: {settings.MONITOR_MEMORY_THRESHOLD}%)"
            )
            
        # Disk threshold
        if stats["disk"] > settings.MONITOR_DISK_THRESHOLD:
            alert_messages.append(
                f"System disk at {stats['disk']:.1f}% (threshold: {settings.MONITOR_DISK_THRESHOLD}%)"
            )
            
        if alert_messages:
            self.alerts["system"] = now
            return "System resource alert: " + ", ".join(alert_messages)
            
        return None

# Global alert manager instance
alert_manager = AlertManager() 