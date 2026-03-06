import time

# ==================== PERFORMANCE MONITOR ====================
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'task_duration': [],
            'success_rate': [],
            'device_uptime': [],
            'tasks_completed': 0,
            'tasks_failed': 0
        }
    
    def start_task_timer(self, task_id):
        self.current_task = {'id': task_id, 'start_time': time.time()}
    
    def end_task_timer(self, success=True):
        if hasattr(self, 'current_task'):
            duration = time.time() - self.current_task['start_time']
            self.metrics['task_duration'].append(duration)
            self.metrics['success_rate'].append(success)
            if success:
                self.metrics['tasks_completed'] += 1
            else:
                self.metrics['tasks_failed'] += 1
    
    def get_average_duration(self):
        if self.metrics['task_duration']:
            return sum(self.metrics['task_duration']) / len(self.metrics['task_duration'])
        return 0
    
    def get_success_rate(self):
        if self.metrics['success_rate']:
            return (sum(self.metrics['success_rate']) / len(self.metrics['success_rate'])) * 100
        return 0
    
    def get_total_tasks(self):
        return self.metrics['tasks_completed'] + self.metrics['tasks_failed']
    
    def get_stats(self):
        return {
            'total_tasks': self.get_total_tasks(),
            'success_rate': self.get_success_rate(),
            'avg_duration': self.get_average_duration(),
            'completed': self.metrics['tasks_completed'],
            'failed': self.metrics['tasks_failed']
        }