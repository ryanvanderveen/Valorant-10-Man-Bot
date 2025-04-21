import discord
from discord.ext import commands
import aiohttp
import html
import random
from datetime import datetime, timezone, timedelta
import asyncio

class PPMinigames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Trivia State
        self.current_trivia_question = None
        self.trivia_timeout = 30
        self.trivia_reward = 1

        # Duel State
        self.pending_duels = {}
        self.duel_timeout_seconds = 60

        # PP Off State
        self.pp_off_active = False
        self.pp_off_end_time = None
        self.pp_off_participants = {}
        self.pp_off_channel = None

    async def _get_db(self):
        """Get database pool from PPDB cog"""
        db_cog = self.bot.get_cog('PPDB')
        if not db_cog:
            raise RuntimeError("PPDB cog not loaded!")
        return await db_cog.get_db()

    def is_pp_off_active(self, channel_id: int) -> bool:
        """Check if PP Off is active in the given channel"""
        return (self.pp_off_active and 
                self.pp_off_channel and 
                self.pp_off_channel.id == channel_id)

    def record_pp_off_score(self, user_id: int, score: int):
        """Record a score for PP Off if it's higher than their previous best"""
        if self.pp_off_active:
            current_highest = self.pp_off_participants.get(user_id, -1)
            if score > current_highest:
                self.pp_off_participants[user_id] = score
                print(f"PP Off: Recorded score {score} for User ID {user_id}")

    @commands.command()
    @commands.guild_only()
    async def duel(self, ctx, challenged_user: discord.Member):
        """Challenges another member to a PP duel!"""
        challenger = ctx.author

        # Input Checks
        if challenger == challenged_user:
            await ctx.send(f"{challenger.mention}, you can't duel yourself! Find a worthy opponent.")
            return
        if challenged_user.bot:
            await ctx.send(f"{challenger.mention}, you can't duel a bot. They have no PP to measure!")
            return

        # Clear expired duels
        await self._clear_expired_duels()

        # Check existing duels
        if await self._is_user_in_duel(challenger.id):
            await ctx.send(f"{challenger.mention}, you are already involved in a duel request. Wait for it to resolve or expire.")
            return
        if await self._is_user_in_duel(challenged_user.id):
            if challenged_user.id in self.pending_duels and self.pending_duels[challenged_user.id]['challenger'] == challenger.id:
                await ctx.send(f"{challenger.mention}, you have already challenged {challenged_user.mention}. They have {self.duel_timeout_seconds} seconds to accept.")
            else:
                await ctx.send(f"{challenger.mention}, {challenged_user.display_name} is already involved in another duel request.")
            return

        # Create Duel Request
        now_utc = datetime.now(timezone.utc)
        self.pending_duels[challenged_user.id] = {
            'challenger': challenger.id,
            'timestamp': now_utc
        }

        await ctx.send(
            f"⚔️ {challenger.mention} has challenged {challenged_user.mention} to a PP duel! ⚔️\n"
            f"{challenged_user.mention}, type `pls accept {challenger.mention}` within {self.duel_timeout_seconds} seconds to accept!"
        )

    @commands.command()
    @commands.guild_only()
    async def accept(self, ctx, challenger_user: discord.Member):
        """Accepts a pending duel challenge."""
        acceptor = ctx.author
        await self._clear_expired_duels()

        pending_request = self.pending_duels.get(acceptor.id)
        if not pending_request:
            await ctx.send(f"{acceptor.mention}, you don't have any pending duel requests to accept.")
            return

        if pending_request['challenger'] != challenger_user.id:
            actual_challenger = ctx.guild.get_member(pending_request['challenger'])
            actual_challenger_name = actual_challenger.mention if actual_challenger else f"User ID {pending_request['challenger']}"
            await ctx.send(f"{acceptor.mention}, you were challenged by {actual_challenger_name}, not {challenger_user.mention}.")
            return

        # Remove pending request and perform duel
        del self.pending_duels[acceptor.id]
        challenger_roll = await self._perform_duel_roll(challenger_user.id)
        acceptor_roll = await self._perform_duel_roll(acceptor.id)

        result_message = (
            f"🔥 **Duel Result!** 🔥\n"
            f"{challenger_user.mention} rolled: **{challenger_roll} inches**\n"
            f"{acceptor.mention} rolled: **{acceptor_roll} inches**\n\n"
        )

        if challenger_roll > acceptor_roll:
            result_message += f"🏆 **{challenger_user.mention} wins the duel!** 🏆"
        elif acceptor_roll > challenger_roll:
            result_message += f"🏆 **{acceptor.mention} wins the duel!** 🏆"
        else:
            result_message += f"🤝 It's a **draw**! A rare display of equal PP prowess! 🤝"

        await ctx.send(result_message)

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.guild_only()
    async def trivia(self, ctx):
        """Asks a trivia question from the Open Trivia Database."""
        if self.current_trivia_question:
            try:
                existing_msg = await self.current_trivia_question['channel'].fetch_message(self.current_trivia_question['message_id'])
                await ctx.send(f"A trivia question is already active! Answer it first: {existing_msg.jump_url}")
                return
            except (discord.NotFound, discord.Forbidden):
                self.current_trivia_question = None

        # Categories: 11=Film, 14=TV, 15=Video Games, 32=Cartoons/Animations
        category_id = random.choice([11, 14, 15, 32])
        api_url = f"https://opentdb.com/api.php?amount=1&type=multiple&category={category_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        await ctx.send("Sorry, couldn't fetch a trivia question right now.")
                        ctx.command.reset_cooldown(ctx)
                        return
                    
                    data = await response.json()
                    if data['response_code'] != 0:
                        await ctx.send("Sorry, couldn't get a unique trivia question. Try again later.")
                        ctx.command.reset_cooldown(ctx)
                        return

                    question_data = data['results'][0]
                    question = html.unescape(question_data['question'])
                    correct_answer = html.unescape(question_data['correct_answer'])
                    incorrect_answers = [html.unescape(ans) for ans in question_data['incorrect_answers']]
                    
                    all_answers = incorrect_answers + [correct_answer]
                    random.shuffle(all_answers)
                    
                    choices_text = "\n".join([f"**{chr(65+i)}.** {choice}" for i, choice in enumerate(all_answers)])
                    
                    embed = discord.Embed(
                        title=f"🧠 Trivia Time! ({question_data['category']})",
                        description=f"**{question}**\n\n{choices_text}",
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text=f"You have {self.trivia_timeout} seconds to answer with A, B, C, or D!")
                    
                    trivia_msg = await ctx.send(embed=embed)
                    
                    self.current_trivia_question = {
                        'question': question,
                        'correct_answer': correct_answer,
                        'choices': all_answers,
                        'channel': ctx.channel,
                        'message_id': trivia_msg.id,
                        'ask_time': datetime.now(timezone.utc),
                        'answered_users': set()
                    }
                    
                    self.bot.loop.create_task(self._trivia_timeout_check(ctx.channel.id, trivia_msg.id, self.trivia_timeout))

            except Exception as e:
                await ctx.send("An error occurred while fetching trivia.")
                ctx.command.reset_cooldown(ctx)
                print(f"Trivia error: {e}")

    @commands.command(name="ppoff")
    @commands.guild_only()
    async def ppoff(self, ctx, duration_minutes: int = 1):
        """Starts a PP Off event! Highest 'pls pp' roll in the duration wins."""
        if self.pp_off_active:
            time_left = self.pp_off_end_time - datetime.now(timezone.utc)
            await ctx.send(f"A PP Off is already in progress! It ends in {time_left.total_seconds() / 60:.1f} minutes.")
            return

        if duration_minutes <= 0 or duration_minutes > 60:
            await ctx.send("Please specify a duration between 1 and 60 minutes.")
            return

        self.pp_off_active = True
        self.pp_off_end_time = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        self.pp_off_participants = {}
        self.pp_off_channel = ctx.channel

        await ctx.send(
            f"🚨 **PP Off has begun!** 🚨\n"
            f"Use `pls pp`! Highest roll in the next **{duration_minutes} minute(s)** wins!\n"
            f"Ends at: {discord.utils.format_dt(self.pp_off_end_time, style='T')}"
        )

        self.bot.loop.create_task(self._schedule_ppoff_end(duration_minutes * 60))

    # Helper Methods
    async def _clear_expired_duels(self):
        """Removes duel requests older than the timeout."""
        now_utc = datetime.now(timezone.utc)
        expired_keys = [
            challenged_id for challenged_id, request in self.pending_duels.items()
            if (now_utc - request['timestamp']).total_seconds() > self.duel_timeout_seconds
        ]
        for key in expired_keys:
            del self.pending_duels[key]

    async def _is_user_in_duel(self, user_id: int) -> bool:
        """Check if a user is either challenging or being challenged."""
        if user_id in self.pending_duels:
            return True
        return any(request['challenger'] == user_id for request in self.pending_duels.values())

    async def _perform_duel_roll(self, user_id: int) -> int:
        """Performs a PP roll for a duel, including event/item effects."""
        sizes = list(range(21))
        weights = [
            1,  2,  3,  5,  7,  10,  15,  18,  20,  25,
            30, 30, 25, 20, 15, 10,  7,   5,   3,   2,
            1
        ]

        base_size = random.choices(sizes, weights=weights, k=1)[0]
        final_size = base_size

        # Get event effect if available
        event_cog = self.bot.get_cog('PPEvents')
        if event_cog:
            event_effect = event_cog.get_current_event_effect()
            if event_effect:
                final_size += event_effect['effect']

        # Get active effects from database
        db = await self._get_db()
        async with db.acquire() as conn:
            active_boost = await conn.fetchrow("""
                SELECT effect_value FROM user_active_effects 
                WHERE user_id = $1 AND effect_type = 'pp_boost' AND end_time > NOW()
            """, user_id)
            
            if active_boost:
                final_size += active_boost['effect_value']

        return max(0, min(20, final_size))

    async def _trivia_timeout_check(self, channel_id, message_id, delay):
        """Checks if a trivia question timed out."""
        await asyncio.sleep(delay)
        if (self.current_trivia_question and
            self.current_trivia_question['channel'].id == channel_id and
            self.current_trivia_question['message_id'] == message_id):
            
            channel = self.current_trivia_question['channel']
            correct_answer = self.current_trivia_question['correct_answer']
            self.current_trivia_question = None

            try:
                await channel.send(f"⏰ Time's up! The correct answer was: **{correct_answer}**")
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Error sending trivia timeout message: {e}")

    async def _schedule_ppoff_end(self, delay_seconds: int):
        """Waits for the duration then triggers PP Off results calculation."""
        await asyncio.sleep(delay_seconds)
        await self._calculate_and_announce_ppoff_results()

    async def _calculate_and_announce_ppoff_results(self):
        """Calculates and announces the winner of the PP Off event."""
        if not self.pp_off_channel:
            self.pp_off_active = False
            self.pp_off_participants = {}
            self.pp_off_end_time = None
            return

        if not self.pp_off_participants:
            await self.pp_off_channel.send("🏁 The PP Off has ended! Nobody participated. 🤷‍♂️")
        else:
            winner_id = max(self.pp_off_participants, key=self.pp_off_participants.get)
            winning_score = self.pp_off_participants[winner_id]

            winner_user = self.bot.get_user(winner_id)
            if not winner_user:
                try:
                    winner_user = await self.bot.fetch_user(winner_id)
                except discord.NotFound:
                    winner_mention = f"User ID {winner_id}"
                except Exception as e:
                    print(f"Error fetching winner user {winner_id}: {e}")
                    winner_mention = f"User ID {winner_id}"
            
            if winner_user:
                winner_mention = winner_user.mention

            sorted_participants = sorted(
                self.pp_off_participants.items(),
                key=lambda item: item[1],
                reverse=True
            )
            results_text = "\n".join([
                f"- <@{uid}>: **{score} inches**"
                for uid, score in sorted_participants[:10]
            ])

            embed = discord.Embed(
                title="🏁 PP Off Results! 🏁",
                description=f"The PP Off has concluded! Congratulations to **{winner_mention}** for achieving the highest score of **{winning_score} inches**! 🎉",
                color=discord.Color.gold()
            )
            if results_text:
                embed.add_field(name="Top Scores:", value=results_text, inline=False)

            await self.pp_off_channel.send(embed=embed)

        self.pp_off_active = False
        self.pp_off_participants = {}
        self.pp_off_channel = None
        self.pp_off_end_time = None

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle trivia answers"""
        if message.author.bot:
            return

        if not self.current_trivia_question:
            return

        if message.channel.id != self.current_trivia_question['channel'].id:
            return

        content_lower = message.content.strip().lower()
        if len(content_lower) != 1 or content_lower not in 'abcd':
            return

        if message.author.id in self.current_trivia_question['answered_users']:
            return

        self.current_trivia_question['answered_users'].add(message.author.id)
        choice_index = ord(content_lower) - ord('a')
        chosen_answer = self.current_trivia_question['choices'][choice_index]
        correct_answer = self.current_trivia_question['correct_answer']

        if chosen_answer == correct_answer:
            winner = message.author
            question_msg_id = self.current_trivia_question['message_id']
            self.current_trivia_question = None

            # Award Reroll Token
            db = await self._get_db()
            try:
                async with db.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO user_inventory (user_id, item_id, quantity)
                        VALUES ($1, 4, 1)
                        ON CONFLICT (user_id, item_id)
                        DO UPDATE SET quantity = user_inventory.quantity + 1
                    """, winner.id)
                await message.channel.send(
                    f"🎉 Correct, {winner.mention}! The answer was **{correct_answer}**. "
                    "You won a **Reroll Token**! 🎉"
                )
            except Exception as e:
                print(f"Error giving trivia reward: {e}")
                await message.channel.send(
                    f"🎉 Correct, {winner.mention}! The answer was **{correct_answer}**. "
                    "(Error giving item reward) 🎉"
                )
        else:
            await message.reply(
                f"❌ Incorrect, {message.author.mention}! That's not the right answer. "
                "Try again next time!",
                delete_after=10
            )

async def setup(bot):
    await bot.add_cog(PPMinigames(bot))
    print("✅ PPMinigames Cog loaded")
