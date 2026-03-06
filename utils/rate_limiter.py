import time

# ==================== RATE LIMITER ====================
class RateLimiter:
    def __init__(self, max_actions_per_hour=100):
        self.max_actions = max_actions_per_hour
        self.action_log = []
    
    def can_perform_action(self, action_type):
        # Remove actions older than 1 hour
        one_hour_ago = time.time() - 3600
        self.action_log = [t for t in self.action_log if t > one_hour_ago]
        
        if len(self.action_log) < self.max_actions:
            self.action_log.append(time.time())
            return True
        return False
    
    def get_remaining_actions(self):
        one_hour_ago = time.time() - 3600
        self.action_log = [t for t in self.action_log if t > one_hour_ago]
        return self.max_actions - len(self.action_log)
    
    def get_wait_time(self):
        if not self.action_log:
            return 0
        
        one_hour_ago = time.time() - 3600
        self.action_log = [t for t in self.action_log if t > one_hour_ago]
        
        if len(self.action_log) < self.max_actions:
            return 0
        
        # Return time until the oldest action is more than 1 hour old
        oldest_action = min(self.action_log)
        return (oldest_action + 3600) - time.time()