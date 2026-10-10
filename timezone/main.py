#importing time based libraries
import time
from datetime import datetime, timedelta
class Timezone:
    def __init__(self, timezone_offset):
        self.timezone_offset = timezone_offset

    def get_current_time(self):
        # Get the current UTC time
        utc_time = time.gmtime()
        # Apply the timezone offset
        local_time = utc_time + timedelta(hours=self.timezone_offset)
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
    
Timezone_offset = int(input("Enter the timezone offset (in hours): "))
timezone = Timezone(Timezone_offset)

current_time = timezone.get_current_time()
print(f"The current time in the specified timezone is: {current_time}")
