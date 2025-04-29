import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import random
import pytz

# Event Definitions
EVENTS = [
    {
        "name": "Heat Wave",
        "effect": 2,
        "duration_hours": 1,
        "start_msg": "☀️ **Heat Wave!** Things are heating up! All pp rolls get a +2 bonus for the next hour!",
        "end_msg": "☀️ The Heat Wave has subsided. PP rolls are back to normal.",
        "color": discord.Color.orange()
    },
    {
        "name": "Cold Snap",
        "effect": -2,
        "duration_hours": 1,
        "start_msg": "❄️ **Cold Snap!** Brrr! It's chilly... all pp rolls get a -2 penalty for the next hour!",
        "end_msg": "❄️ The Cold Snap has passed. PP rolls are back to normal.",
        "color": discord.Color.blue()
    },
    {
        "name": "Growth Spurt",
        "effect": 1,
        "duration_hours": 2,
        "start_msg": "🌱 **Growth Spurt!** Favorable conditions! All pp rolls get a +1 bonus for the next 2 hours!",
        "end_msg": "🌱 The Growth Spurt is over. PP rolls are back to normal.",
        "color": discord.Color.green()
    },
    {
        "name": "Shrinkage",
        "effect": -1,
        "duration_hours": 2,
        "start_msg": "🥶 **Shrinkage!** Uh oh... All pp rolls get a -1 penalty for the next 2 hours!",
        "end_msg": "🥶 The Shrinkage effect has worn off. PP rolls are back to normal.",
        "color": discord.Color.light_grey()
    }
]

class PPEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ET_TIMEZONE = pytz.timezone("America/New_York")
        self.current_event = None
        self.event_end_time = None
        self.event_effect = 0
        self.announcement_channel = None
        self.event_task.start()
        # self.random_event_task.start()  # Disabled: events now only checked at the top of the hour

    def get_current_event_effect(self):
        """Returns the current event effect if one is active"""
        if self.current_event and datetime.now(timezone.utc) < self.event_end_time:
            return {
                'name': self.current_event['name'],
                'effect': self.event_effect
            }
        return None

    # @tasks.loop(seconds=60)
    # async def random_event_task(self):
    #     """Randomly triggers global events throughout the day. (DISABLED)"""
    #     pass

    @tasks.loop(hours=1)
    async def event_task(self):
        """Handles event cycling and management"""
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(self.ET_TIMEZONE)
        print(f" Running event check at {now_utc.isoformat()} (ET: {now_et.strftime('%Y-%m-%d %H:%M:%S')})...")

        # Check if current event has ended
        if self.current_event and now_utc >= self.event_end_time:
            print(f" Event '{self.current_event['name']}' ended.")
            if self.announcement_channel:
                embed = discord.Embed(description=self.current_event['end_msg'], color=self.current_event['color'])
                try:
                    await self.announcement_channel.send(embed=embed)
                except discord.Forbidden:
                    print(f" Error: Bot lacks permission to send messages in {self.announcement_channel.name}")
                except Exception as e:
                    print(f" Error sending event end message: {e}")
            self.current_event = None
            self.event_end_time = None
            self.event_effect = 0

        # Attempt to start a new event
        elif not self.current_event:
            # Allowed hours: 8 AM to 1 AM ET (inclusive)
            # Disallowed hours: 2, 3, 4, 5, 6, 7
            if now_et.hour not in [2, 3, 4, 5, 6, 7]:
                # Make events rare: 5% chance per hour
                if random.randint(1, 100) <= 5:  # 5% chance every hour during allowed times
                    self.current_event = random.choice(EVENTS)
                    duration = timedelta(hours=self.current_event['duration_hours'])
                    event_start_time = now_utc.replace(minute=0, second=0, microsecond=0)
                    self.event_end_time = event_start_time + duration
                    self.event_effect = self.current_event['effect']
                    print(f" Starting event: {self.current_event['name']} for {self.current_event['duration_hours']} hour(s)")

                    if self.announcement_channel:
                        embed = discord.Embed(
                            title=f"📢 Server Event: {self.current_event['name']}!",
                            description=self.current_event['start_msg'],
                            color=self.current_event['color']
                        )
                        embed.set_footer(text=f"This event will last for {self.current_event['duration_hours']} hour(s). Started at {now_et.strftime('%I:%M %p %Z')}")
                        try:
                            await self.announcement_channel.send(embed=embed)
                        except discord.Forbidden:
                            print(f" Error: Bot lacks permission to send messages in {self.announcement_channel.name}")
                        except Exception as e:
                            print(f" Error sending event start message: {e}")
                else:
                    print(" Rolled dice, but no new event started this hour.")
            else:
                print(f" Outside allowed time window (2 AM - 7:59 AM ET). No event check performed.")
        else:
            remaining_time = self.event_end_time - now_utc
            print(f" Event '{self.current_event['name']}' is still active. Time remaining: {remaining_time}")

    @event_task.before_loop
    async def before_event_task(self):
        """Setup before starting the event task loop"""
        await self.bot.wait_until_ready()
        print(" Event Task Loop Ready. Waiting for next hour to start checks...")

        # Wait until the top of the next hour
        now = datetime.now(timezone.utc)
        seconds_past_hour = now.minute * 60 + now.second + now.microsecond / 1_000_000
        seconds_until_next_hour = 3600 - seconds_past_hour
        if seconds_until_next_hour > 0:
            print(f" Waiting {seconds_until_next_hour:.2f} seconds for the next hour...")
            await asyncio.sleep(seconds_until_next_hour)
        print(" Reached the top of the hour. Starting event loop.")

        # Find Announcement Channel
        announcement_channel_id = 934181022659129444  # Hardcoded Channel ID
        self.announcement_channel = self.bot.get_channel(announcement_channel_id)
        
        if self.announcement_channel:
            print(f" Found announcement channel: #{self.announcement_channel.name}")
        else:
            print(f" Warning: Could not find announcement channel with ID {announcement_channel_id}")

    @event_task.after_loop
    async def after_event_task(self):
        """Cleanup after the event task loop ends"""
        pass

async def setup(bot):
    await bot.add_cog(PPEvents(bot))
    print("✅ PPEvents Cog loaded")
