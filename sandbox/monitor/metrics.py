from prometheus_client import Counter, Gauge, Histogram, start_http_server
from sandbox.config import settings
from sandbox.monitor.alerts import alert_manager
import psutil
import time
import asyncio
import logging

logger = logging.getLogger(__name__)

# Metrics
sandbox_container_count = Gauge('sandbox_container_count', 'Number of running sandboxes')
sandbox_cpu_usage = Gauge('sandbox_cpu_usage_percent', 'CPU usage per sandbox', ['container_id'])
sandbox_memory_usage = Gauge('sandbox_memory_usage_bytes', 'Memory usage per sandbox', ['container_id'])
sandbox_network_rx = Counter('sandbox_network_rx_bytes', 'Network bytes received', ['container_id'])
sandbox_network_tx = Counter('sandbox_network_tx_bytes', 'Network bytes transmitted', ['container_id'])
sandbox_disk_usage = Gauge('sandbox_disk_usage_bytes', 'Disk usage per sandbox', ['container_id'])
sandbox_uptime = Gauge('sandbox_uptime_seconds', 'Sandbox uptime in seconds', ['container_id'])

# System metrics
system_cpu_usage = Gauge('system_cpu_usage_percent', 'System CPU usage')
system_memory_usage = Gauge('system_memory_usage_percent', 'System memory usage')
system_disk_usage = Gauge('system_disk_usage_percent', 'System disk usage')

# Additional metrics for alerts
alert_count = Counter('sandbox_alerts_total', 'Total number of alerts', ['type'])
resource_threshold_violations = Counter('sandbox_resource_violations_total', 'Resource threshold violations', ['resource', 'container_id'])

class MetricsCollector:
    def __init__(self, docker_manager):
        self.docker_manager = docker_manager
        self.running = False
        
    async def start(self):
        """Start metrics collection"""
        if settings.METRICS_ENABLED:
            # Start Prometheus HTTP server
            start_http_server(settings.PROMETHEUS_PORT)
            self.running = True
            asyncio.create_task(self._collect_metrics())
            logger.info(f"Metrics server started on port {settings.PROMETHEUS_PORT}")
            
    async def stop(self):
        """Stop metrics collection"""
        self.running = False
        
    async def _collect_metrics(self):
        """Collect metrics periodically"""
        while self.running:
            try:
                # Update system metrics
                system_cpu = psutil.cpu_percent()
                system_memory = psutil.virtual_memory().percent
                system_disk = psutil.disk_usage('/').percent
                
                system_cpu_usage.set(system_cpu)
                system_memory_usage.set(system_memory)
                system_disk_usage.set(system_disk)
                
                # Check system alerts
                system_alert = alert_manager.check_system_stats({
                    "cpu": system_cpu,
                    "memory": system_memory,
                    "disk": system_disk
                })
                
                if system_alert:
                    alert_count.labels("system").inc()
                    logger.warning(system_alert)
                
                # Update container metrics
                containers = await self.docker_manager.list_containers("running")
                sandbox_container_count.set(len(containers))
                
                for container in containers:
                    container_id = container["container_id"]
                    stats = await self.docker_manager.get_container_stats(container_id)
                    
                    if stats:
                        # Update metrics
                        sandbox_cpu_usage.labels(container_id).set(stats["cpu_percent"])
                        sandbox_memory_usage.labels(container_id).set(stats["memory_usage"])
                        sandbox_network_rx.labels(container_id).inc(stats["network_rx"])
                        sandbox_network_tx.labels(container_id).inc(stats["network_tx"])
                        sandbox_disk_usage.labels(container_id).set(stats["disk_usage"])
                        sandbox_uptime.labels(container_id).set(stats["uptime"])
                        
                        # Check alerts
                        container_alert = alert_manager.check_container_stats(container_id, stats)
                        if container_alert:
                            alert_count.labels("container").inc()
                            logger.warning(container_alert)
                            
                            # Track specific violations
                        # Check thresholds and log warnings
                        if stats["cpu_percent"] > settings.MONITOR_CPU_THRESHOLD:
                            logger.warning(f"Container {container_id} CPU usage above threshold: {stats['cpu_percent']}%")
                        if stats["memory_usage"] / stats["memory_limit"] * 100 > settings.MONITOR_MEMORY_THRESHOLD:
                            logger.warning(f"Container {container_id} memory usage above threshold")
                
            except Exception as e:
                logger.error(f"Error collecting metrics: {str(e)}")
                
            await asyncio.sleep(settings.MONITOR_INTERVAL) 