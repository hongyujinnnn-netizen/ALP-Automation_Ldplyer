import random

# ==================== ACTIVITY RANDOMIZER ====================
class ActivityRandomizer:
    @staticmethod
    def random_delay(base_delay, variation=0.3):
        variation_amount = base_delay * variation
        return max(0.1, base_delay + random.uniform(-variation_amount, variation_amount))
    
    @staticmethod
    def random_swipe_pattern():
        patterns = ["straight", "curve", "zigzag"]
        return random.choice(patterns)
    
    @staticmethod
    def random_swipe_duration(base_duration, variation=0.2):
        return ActivityRandomizer.random_delay(base_duration, variation)
    
    @staticmethod
    def generate_random_hashtags():
        hashtag_groups = [
            "#reels #viral #trending #fyp #foryou #foryoupage #explorepage #instagramreels #reelitfeelit #reelkarofeelkaro #reelsindia #reelsteady #reelsvideo #reelsinsta #reelslovers #reelsofinstagram #reelsviral #reelsdance #reelsmusic #reelsfunny",
            "#viralvideo #trendingnow #fypシ #foryourpage #explore #instareels #reelit #reelkarofeelkaro #reelsindia #reelsteadygo #reelsvideoviral #reelsinstagram #reelslover #reelsofig #reelsviraltrick #reelsdancevideo #reelsmusicvideo #reelsfunnyvideos #contentcreator #digitalcreator",
            "#reels #viral #fyp #trending #foryou #instagramreels #reelitfeelit #reelsindia #reelsteady #reelsvideo #explorepage #foryoupage #reelsinsta #reelslovers #reelsofinstagram #reelsviral #reelsdance #reelsmusic #reelsfunny #contentcreation"
        ]
        return random.choice(hashtag_groups)