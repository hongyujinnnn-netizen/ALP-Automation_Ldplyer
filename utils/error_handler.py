# ==================== ENHANCED ERROR HANDLER ====================
class EnhancedErrorHandler:
    def __init__(self, log_func):
        self.log = log_func
        self.error_count = {}
        self.max_retries = 3
        
    def handle_adb_error(self, device_name, operation, error):
        key = f"{device_name}_{operation}"
        self.error_count[key] = self.error_count.get(key, 0) + 1
        
        if self.error_count[key] <= self.max_retries:
            self.log(f"🔄 Retrying {operation} on {device_name} (attempt {self.error_count[key]})")
            return True
        else:
            self.log(f"❌ Max retries exceeded for {operation} on {device_name}")
            return False
            
    def reset_counters(self, device_name=None):
        if device_name:
            keys = [k for k in self.error_count.keys() if device_name in k]
            for key in keys:
                del self.error_count[key]
        else:
            self.error_count.clear()