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
        self.trivia_timeout = 15
        self.trivia_reward = 1
        self._last_trivia_time = {}

        # Duel State
        self.pending_duels = {}
        self.duel_timeout_seconds = 60

        # PP Off State
        self.pp_off_active = False
        self.pp_off_end_time = None
        self.pp_off_participants = {}
        self.pp_off_channel = None

        # Word Scramble State
        self.current_scramble = None
        self.scramble_timeout = 20

        # Higher/Lower State
        self.current_highlow = None
        self.highlow_timeout = 15

        # Math Rush State
        self.current_math = None
        self.math_timeout = 10

        # Blackjack State
        self.active_blackjack_games = {}  # user_id: game_data

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
            actual_challenger_name = actual_challenger.mention if actual_challenger else f"<@{pending_request['challenger']}>"
            await ctx.send(f"{acceptor.mention}, you were challenged by {actual_challenger_name}, not {challenger_user.mention}.")
            return

        # Remove pending request and perform duel
        del self.pending_duels[acceptor.id]
        challenger_roll = await self._perform_duel_roll(challenger_user.id)
        acceptor_roll = await self._perform_duel_roll(acceptor.id)

        # Get profile cog and DB for stat updates/achievements
        profile_cog = self.bot.get_cog('PPProfile')
        db = await self._get_db()

        result_message = (
            f"🔥 **Duel Result!** 🔥\n"
            f"{challenger_user.mention} rolled: **{challenger_roll} inches**\n"
            f"{acceptor.mention} rolled: **{acceptor_roll} inches**\n\n"
        )

        winner = None # Keep track of the winner
        if challenger_roll > acceptor_roll:
            result_message += f"🏆 **{challenger_user.mention} wins the duel!** 🏆"
            winner = challenger_user
        elif acceptor_roll > challenger_roll:
            result_message += f"🏆 **{acceptor.mention} wins the duel!** 🏆"
            winner = acceptor
        else:
            result_message += f"🤝 It's a **draw**! A rare display of equal PP prowess! 🤝"

        # Update stats and check achievements if there's a winner
        if winner and profile_cog:
            try:
                async with db.acquire() as conn:
                    async with conn.transaction(): # Use transaction for atomicity
                        # Increment duel_wins and get the new count
                        new_stats = await conn.fetchrow("""
                            INSERT INTO user_stats (user_id, duel_wins) VALUES ($1, 1)
                            ON CONFLICT (user_id) DO UPDATE SET
                                duel_wins = user_stats.duel_wins + 1
                            RETURNING duel_wins
                            """, winner.id)
                        new_duel_wins = new_stats['duel_wins'] if new_stats else 1
                        print(f"[Stats] Updated duel_wins for {winner.name} ({winner.id}) to {new_duel_wins}")

                        # Grant achievements based on the new count
                        if new_duel_wins == 1:
                            await profile_cog._grant_achievement(winner, 'first_duel_win', ctx)
                        if new_duel_wins == 10:
                            await profile_cog._grant_achievement(winner, 'ten_duel_wins', ctx)

            except Exception as e:
                print(f"Error updating duel stats/achievements for {winner.name}: {e}")
                import traceback
                traceback.print_exc()

        await ctx.send(result_message)

    @commands.command()
    @commands.guild_only()
    async def trivia(self, ctx):
        """Asks a trivia question from the Open Trivia Database."""
        # First check if a trivia is already active
        if self.current_trivia_question:
            try:
                existing_msg = await self.current_trivia_question['channel'].fetch_message(self.current_trivia_question['message_id'])
                await ctx.send(f"A trivia question is already active! Answer it first: {existing_msg.jump_url}")
                return
            except (discord.NotFound, discord.Forbidden):
                self.current_trivia_question = None
        
        # Check for cooldown using a custom cooldown system
        # This is more reliable than the built-in cooldown decorator
        current_time = datetime.now(timezone.utc)
        guild_id = ctx.guild.id
        
        # Make sure we have the cooldown tracking dictionary
        if not hasattr(self, '_last_trivia_time'):
            self._last_trivia_time = {}
        
        # Check if this guild has used trivia recently
        if guild_id in self._last_trivia_time:
            time_diff = (current_time - self._last_trivia_time[guild_id]).total_seconds()
            if time_diff < 60:  # 60 second cooldown
                seconds_left = int(60 - time_diff)
                minutes, seconds = divmod(seconds_left, 60)
                cooldown_msg = f"{ctx.author.mention}, this command is on cooldown! Try again in "
                if minutes > 0:
                    cooldown_msg += f"{minutes} minute{'s' if minutes > 1 else ''} and "
                cooldown_msg += f"{seconds} second{'s' if seconds != 1 else ''}."
                await ctx.send(cooldown_msg)
                return
        
        # Using The Trivia API - more questions, better variety!
        # Categories: film_and_tv, music, sport_and_leisure, arts_and_literature, history, society_and_culture, science, geography, food_and_drink, general_knowledge
        categories = ['film_and_tv', 'music', 'sport_and_leisure', 'general_knowledge', 'science']
        category = random.choice(categories)
        difficulties = ['easy', 'medium', 'hard']
        difficulty = random.choice(difficulties)

        api_url = f"https://the-trivia-api.com/v2/questions?limit=1&categories={category}&difficulties={difficulty}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        await ctx.send("Sorry, couldn't fetch a trivia question right now.")
                        return

                    data = await response.json()
                    if not data or len(data) == 0:
                        await ctx.send("Sorry, couldn't get a trivia question. Try again later.")
                        return

                    question_data = data[0]
                    question = question_data['question']['text']
                    correct_answer = question_data['correctAnswer']
                    incorrect_answers = question_data['incorrectAnswers']

                    all_answers = incorrect_answers + [correct_answer]
                    random.shuffle(all_answers)

                    choices_text = "\n".join([f"**{chr(65+i)}.** {choice}" for i, choice in enumerate(all_answers)])

                    # Format category name nicely
                    category_display = question_data['category'].replace('_', ' ').title()
                    difficulty_emoji = "🟢" if difficulty == "easy" else "🟡" if difficulty == "medium" else "🔴"

                    embed = discord.Embed(
                        title=f"🧠 Trivia Time! {difficulty_emoji}",
                        description=f"**{question}**\n\n{choices_text}",
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text=f"Category: {category_display} | Difficulty: {difficulty.title()} | {self.trivia_timeout}s to answer!")

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
                print(f"Trivia error: {e}")
                import traceback
                traceback.print_exc()

    @commands.command()
    @commands.guild_only()
    async def scramble(self, ctx):
        """Scrambles a word - unscramble it to win an item!"""
        if self.current_scramble:
            try:
                existing_msg = await self.current_scramble['channel'].fetch_message(self.current_scramble['message_id'])
                await ctx.send(f"A scramble is already active! Answer it first: {existing_msg.jump_url}")
                return
            except (discord.NotFound, discord.Forbidden):
                self.current_scramble = None

        # Word bank with varying difficulties
        words = [
            # Easy (5-6 letters)
            'python', 'gaming', 'dragon', 'wizard', 'knight', 'castle', 'forest', 'battle',
            # Medium (7-8 letters)
            'champion', 'treasure', 'valorant', 'diamond', 'keyboard', 'mystery', 'warrior',
            # Hard (9+ letters)
            'legendary', 'adventure', 'challenge', 'iversity', 'lightning', 'dangerous'
        ]

        chosen_word = random.choice(words)
        scrambled = ''.join(random.sample(chosen_word, len(chosen_word)))

        # Make sure it's actually scrambled
        attempts = 0
        while scrambled.lower() == chosen_word.lower() and attempts < 10:
            scrambled = ''.join(random.sample(chosen_word, len(chosen_word)))
            attempts += 1

        difficulty_emoji = "🟢" if len(chosen_word) <= 6 else "🟡" if len(chosen_word) <= 8 else "🔴"

        embed = discord.Embed(
            title=f"📝 Word Scramble! {difficulty_emoji}",
            description=f"**Unscramble this word:**\n\n`{scrambled.upper()}`",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"You have {self.scramble_timeout} seconds! Type your answer in chat.")

        scramble_msg = await ctx.send(embed=embed)

        self.current_scramble = {
            'word': chosen_word.lower(),
            'scrambled': scrambled,
            'channel': ctx.channel,
            'message_id': scramble_msg.id,
            'answered_users': set()
        }

        self.bot.loop.create_task(self._scramble_timeout_check(ctx.channel.id, scramble_msg.id))

    @commands.command()
    @commands.guild_only()
    async def highlow(self, ctx):
        """Guess if the next number will be higher or lower!"""
        if self.current_highlow:
            try:
                existing_msg = await self.current_highlow['channel'].fetch_message(self.current_highlow['message_id'])
                await ctx.send(f"A Higher/Lower game is already active: {existing_msg.jump_url}")
                return
            except (discord.NotFound, discord.Forbidden):
                self.current_highlow = None

        first_number = random.randint(1, 100)
        actual_next = random.randint(1, 100)

        embed = discord.Embed(
            title="🎲 Higher or Lower?",
            description=f"**Current number: {first_number}**\n\nWill the next number be **higher** or **lower**?\n\nType `h` or `higher` for higher\nType `l` or `lower` for lower",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"You have {self.highlow_timeout} seconds to guess!")

        highlow_msg = await ctx.send(embed=embed)

        self.current_highlow = {
            'current_number': first_number,
            'next_number': actual_next,
            'channel': ctx.channel,
            'message_id': highlow_msg.id,
            'answered_users': set()
        }

        self.bot.loop.create_task(self._highlow_timeout_check(ctx.channel.id, highlow_msg.id))

    @commands.command()
    @commands.guild_only()
    async def mathrush(self, ctx):
        """Solve a quick math problem to win an item!"""
        if self.current_math:
            try:
                existing_msg = await self.current_math['channel'].fetch_message(self.current_math['message_id'])
                await ctx.send(f"A Math Rush is already active: {existing_msg.jump_url}")
                return
            except (discord.NotFound, discord.Forbidden):
                self.current_math = None

        # Generate random math problem
        num1 = random.randint(5, 50)
        num2 = random.randint(5, 50)
        operation = random.choice(['+', '-', '*'])

        if operation == '+':
            answer = num1 + num2
            problem = f"{num1} + {num2}"
        elif operation == '-':
            answer = num1 - num2
            problem = f"{num1} - {num2}"
        else:  # multiplication
            num1 = random.randint(2, 12)
            num2 = random.randint(2, 12)
            answer = num1 * num2
            problem = f"{num1} × {num2}"

        embed = discord.Embed(
            title="🧮 Math Rush!",
            description=f"**Solve this:**\n\n`{problem} = ?`",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Quick! You have {self.math_timeout} seconds!")

        math_msg = await ctx.send(embed=embed)

        self.current_math = {
            'answer': answer,
            'problem': problem,
            'channel': ctx.channel,
            'message_id': math_msg.id,
            'answered_users': set()
        }

        self.bot.loop.create_task(self._math_timeout_check(ctx.channel.id, math_msg.id))

    @commands.command(name="wyr")
    @commands.guild_only()
    async def would_you_rather(self, ctx):
        """Presents a 'Would You Rather' question for fun discussion!"""
        # Fun Would You Rather scenarios
        scenarios = [
            ("have the ability to fly", "be invisible"),
            ("fight 100 duck-sized horses", "fight 1 horse-sized duck"),
            ("always win at games but never improve", "always lose but get better every time"),
            ("have unlimited PP coins", "have unlimited items"),
            ("know all languages", "be able to talk to animals"),
            ("live in the past", "live in the future"),
            ("be a master at every game", "be a master chef"),
            ("have super strength", "have super speed"),
            ("never need to sleep", "never need to eat"),
            ("always be 10 minutes late", "always be 20 minutes early"),
            ("have a rewind button for life", "have a pause button for life"),
            ("be famous but poor", "be rich but unknown"),
            ("explore space", "explore the ocean depths"),
            ("have a pet dragon", "have a pet unicorn"),
            ("win every duel", "win every trivia")
        ]

        option_a, option_b = random.choice(scenarios)

        embed = discord.Embed(
            title="🤔 Would You Rather?",
            description=f"**Option A:** {option_a.title()}\n\n**Option B:** {option_b.title()}\n\n React with 🅰️ for A or 🅱️ for B!",
            color=discord.Color.magenta()
        )
        embed.set_footer(text="This is just for fun - no rewards!")

        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🅰️")
        await msg.add_reaction("🅱️")

    @commands.command()
    @commands.guild_only()
    async def blackjack(self, ctx, bet: int = 10):
        """Start a blackjack game! Bet PP coins to win big!"""
        player = ctx.author

        # Check if already in a game
        if player.id in self.active_blackjack_games:
            await ctx.send(f"{player.mention}, you're already in a blackjack game! Use `pls hit` or `pls stand`.")
            return

        # Validate bet amount
        if bet <= 0:
            await ctx.send(f"{player.mention}, you need to bet at least 1 PP coin!")
            return

        # Check if player has enough coins
        db = await self._get_db()
        async with db.acquire() as conn:
            user_data = await conn.fetchrow("SELECT pp_coins FROM user_data WHERE user_id = $1", player.id)
            current_coins = user_data['pp_coins'] if user_data else 0

            if current_coins < bet:
                await ctx.send(f"{player.mention}, you only have **{current_coins}** PP coins! You can't bet {bet}.")
                return

            # Deduct bet from their balance
            await conn.execute("""
                INSERT INTO user_data (user_id, pp_coins) VALUES ($1, -$2)
                ON CONFLICT (user_id) DO UPDATE SET pp_coins = user_data.pp_coins - $2
            """, player.id, bet)
            print(f"[Blackjack] Deducted {bet} PP coins from user {player.id}")

        # Create new game
        deck = self._create_deck()
        random.shuffle(deck)

        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        game_data = {
            'bet': bet,
            'deck': deck,
            'player_hand': player_hand,
            'dealer_hand': dealer_hand,
            'channel': ctx.channel
        }

        self.active_blackjack_games[player.id] = game_data

        # Check for natural blackjack
        player_value = self._calculate_hand(player_hand)
        dealer_value = self._calculate_hand(dealer_hand)

        if player_value == 21:
            await self._end_blackjack_game(player, ctx, "blackjack")
            return

        # Show initial hands
        embed = self._create_blackjack_embed(player, game_data, show_dealer_card=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def hit(self, ctx):
        """Draw another card in your blackjack game"""
        player = ctx.author

        if player.id not in self.active_blackjack_games:
            await ctx.send(f"{player.mention}, you're not in a blackjack game! Start one with `pls blackjack <bet>`.")
            return

        game_data = self.active_blackjack_games[player.id]

        # Check if in correct channel
        if ctx.channel.id != game_data['channel'].id:
            await ctx.send(f"{player.mention}, your blackjack game is in {game_data['channel'].mention}!")
            return

        # Deal a card
        card = game_data['deck'].pop()
        game_data['player_hand'].append(card)

        player_value = self._calculate_hand(game_data['player_hand'])

        # Check for bust
        if player_value > 21:
            await self._end_blackjack_game(player, ctx, "bust")
            return

        # Check for 21
        if player_value == 21:
            await self._end_blackjack_game(player, ctx, "stand")
            return

        # Show updated hand
        embed = self._create_blackjack_embed(player, game_data, show_dealer_card=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def stand(self, ctx):
        """Stand with your current hand in blackjack"""
        player = ctx.author

        if player.id not in self.active_blackjack_games:
            await ctx.send(f"{player.mention}, you're not in a blackjack game! Start one with `pls blackjack <bet>`.")
            return

        game_data = self.active_blackjack_games[player.id]

        # Check if in correct channel
        if ctx.channel.id != game_data['channel'].id:
            await ctx.send(f"{player.mention}, your blackjack game is in {game_data['channel'].mention}!")
            return

        await self._end_blackjack_game(player, ctx, "stand")

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

            # When a trivia times out, we should reset the cooldown for that guild
            guild_id = channel.guild.id
            if hasattr(self, '_last_trivia_time') and guild_id in self._last_trivia_time:
                # Set the time to more than 60 seconds ago to reset cooldown
                self._last_trivia_time[guild_id] = datetime.now(timezone.utc) - timedelta(seconds=61)

            try:
                await channel.send(f"⏰ Time's up! The correct answer was: **{correct_answer}**")
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Error sending trivia timeout message: {e}")

    async def _scramble_timeout_check(self, channel_id, message_id):
        """Checks if a scramble timed out."""
        await asyncio.sleep(self.scramble_timeout)
        if (self.current_scramble and
            self.current_scramble['channel'].id == channel_id and
            self.current_scramble['message_id'] == message_id):

            channel = self.current_scramble['channel']
            correct_word = self.current_scramble['word']
            self.current_scramble = None

            try:
                await channel.send(f"⏰ Time's up! The word was: **{correct_word.upper()}**")
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Error sending scramble timeout message: {e}")

    async def _highlow_timeout_check(self, channel_id, message_id):
        """Checks if a higher/lower game timed out."""
        await asyncio.sleep(self.highlow_timeout)
        if (self.current_highlow and
            self.current_highlow['channel'].id == channel_id and
            self.current_highlow['message_id'] == message_id):

            channel = self.current_highlow['channel']
            next_num = self.current_highlow['next_number']
            current_num = self.current_highlow['current_number']
            result = "higher" if next_num > current_num else "lower" if next_num < current_num else "the same"
            self.current_highlow = None

            try:
                await channel.send(f"⏰ Time's up! The next number was **{next_num}** ({result})!")
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Error sending highlow timeout message: {e}")

    async def _math_timeout_check(self, channel_id, message_id):
        """Checks if a math problem timed out."""
        await asyncio.sleep(self.math_timeout)
        if (self.current_math and
            self.current_math['channel'].id == channel_id and
            self.current_math['message_id'] == message_id):

            channel = self.current_math['channel']
            answer = self.current_math['answer']
            problem = self.current_math['problem']
            self.current_math = None

            try:
                await channel.send(f"⏰ Time's up! The answer was: **{problem} = {answer}**")
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Error sending math timeout message: {e}")

    def _create_deck(self):
        """Create a standard 52-card deck"""
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        deck = []
        for suit in suits:
            for rank in ranks:
                deck.append(f"{rank}{suit}")
        return deck

    def _calculate_hand(self, hand):
        """Calculate the value of a blackjack hand"""
        value = 0
        aces = 0

        for card in hand:
            rank = card[:-1]  # Remove suit
            if rank in ['J', 'Q', 'K']:
                value += 10
            elif rank == 'A':
                aces += 1
                value += 11
            else:
                value += int(rank)

        # Adjust for aces
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1

        return value

    def _format_hand(self, hand, hide_second=False):
        """Format a hand for display"""
        if hide_second and len(hand) > 1:
            return f"{hand[0]} 🂠"
        return " ".join(hand)

    def _create_blackjack_embed(self, player, game_data, show_dealer_card=False, result=None):
        """Create an embed showing the blackjack game state"""
        player_hand = game_data['player_hand']
        dealer_hand = game_data['dealer_hand']
        bet = game_data['bet']

        player_value = self._calculate_hand(player_hand)
        dealer_value = self._calculate_hand(dealer_hand) if show_dealer_card else self._calculate_hand([dealer_hand[0]])

        # Choose color based on result
        if result == "win" or result == "blackjack":
            color = discord.Color.green()
        elif result == "lose" or result == "bust":
            color = discord.Color.red()
        elif result == "push":
            color = discord.Color.yellow()
        else:
            color = discord.Color.blue()

        embed = discord.Embed(
            title="🃏 Blackjack",
            color=color
        )

        # Dealer's hand
        dealer_display = self._format_hand(dealer_hand, hide_second=not show_dealer_card)
        if show_dealer_card:
            embed.add_field(name=f"Dealer's Hand ({dealer_value})", value=dealer_display, inline=False)
        else:
            embed.add_field(name="Dealer's Hand", value=dealer_display, inline=False)

        # Player's hand
        player_display = self._format_hand(player_hand)
        embed.add_field(name=f"{player.display_name}'s Hand ({player_value})", value=player_display, inline=False)

        # Show bet
        embed.add_field(name="Bet", value=f"{bet} PP coins", inline=True)

        # Show result if game is over
        if result:
            if result == "win":
                embed.add_field(name="Result", value=f"🎉 You win {bet * 2} PP coins!", inline=False)
            elif result == "blackjack":
                embed.add_field(name="Result", value=f"🎰 BLACKJACK! You win {int(bet * 2.5)} PP coins!", inline=False)
            elif result == "lose":
                embed.add_field(name="Result", value=f"💔 Dealer wins! You lost {bet} PP coins.", inline=False)
            elif result == "bust":
                embed.add_field(name="Result", value=f"💥 BUST! You lost {bet} PP coins.", inline=False)
            elif result == "push":
                embed.add_field(name="Result", value=f"🤝 Push! Your {bet} PP coins have been returned.", inline=False)
        else:
            embed.set_footer(text="Use 'pls hit' to draw a card or 'pls stand' to hold")

        return embed

    async def _end_blackjack_game(self, player, ctx, action):
        """End a blackjack game and determine winner"""
        game_data = self.active_blackjack_games[player.id]
        bet = game_data['bet']
        player_hand = game_data['player_hand']
        dealer_hand = game_data['dealer_hand']

        player_value = self._calculate_hand(player_hand)

        # Handle bust
        if action == "bust":
            del self.active_blackjack_games[player.id]
            embed = self._create_blackjack_embed(player, game_data, show_dealer_card=True, result="bust")
            await ctx.send(embed=embed)
            return

        # Handle blackjack
        if action == "blackjack":
            dealer_value = self._calculate_hand(dealer_hand)
            if dealer_value == 21:
                # Push
                result = "push"
                winnings = bet
            else:
                # Blackjack pays 2.5x
                result = "blackjack"
                winnings = int(bet * 2.5)
        else:
            # Dealer plays
            while self._calculate_hand(dealer_hand) < 17:
                dealer_hand.append(game_data['deck'].pop())

            dealer_value = self._calculate_hand(dealer_hand)

            # Determine winner
            if dealer_value > 21:
                result = "win"
                winnings = bet * 2
            elif dealer_value > player_value:
                result = "lose"
                winnings = 0
            elif dealer_value < player_value:
                result = "win"
                winnings = bet * 2
            else:
                result = "push"
                winnings = bet

        # Award winnings
        db = await self._get_db()
        async with db.acquire() as conn:
            if winnings > 0:
                await conn.execute("""
                    INSERT INTO user_data (user_id, pp_coins) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET pp_coins = user_data.pp_coins + $2
                """, player.id, winnings)
                print(f"[Blackjack] Awarded {winnings} PP coins to user {player.id}")

        # Clean up and show result
        del self.active_blackjack_games[player.id]
        embed = self._create_blackjack_embed(player, game_data, show_dealer_card=True, result=result)
        await ctx.send(embed=embed)

    async def _award_game_item(self, winner, message, success_message: str):
        """Awards a random item AND PP coins to a game winner (used for scramble, highlow, mathrush)"""
        db = await self._get_db()
        coin_reward = 10  # Award 10 PP coins per game win

        try:
            async with db.acquire() as conn:
                async with conn.transaction():
                    # Award PP coins
                    await conn.execute("""
                        INSERT INTO user_data (user_id, pp_coins) VALUES ($1, $2)
                        ON CONFLICT (user_id) DO UPDATE SET pp_coins = user_data.pp_coins + $2
                    """, winner.id, coin_reward)
                    print(f"[Game Reward] Awarded {coin_reward} PP coins to user {winner.id}")

                    # Get all available items
                    items = await conn.fetch("SELECT item_id, name FROM items")
                    if not items:
                        await message.channel.send(f"{success_message} You earned **{coin_reward} PP coins**! (No items available)")
                        return

                    # Define item rarities (same as trivia)
                    item_weights = {
                        1: 40,  # Growth Potion - common
                        2: 30,  # Shrink Ray - uncommon
                        3: 20,  # Lucky Socks - rare
                        4: 10   # Reroll Token - very rare
                    }

                    # Choose random item based on weights
                    item_ids = [item['item_id'] for item in items]
                    weights = [item_weights.get(item_id, 25) for item_id in item_ids]
                    chosen_item_id = random.choices(item_ids, weights=weights, k=1)[0]
                    chosen_item = next(item for item in items if item['item_id'] == chosen_item_id)

                    # Add item to inventory
                    await conn.execute("""
                        INSERT INTO user_inventory (user_id, item_id, quantity)
                        VALUES ($1, $2, 1)
                        ON CONFLICT (user_id, item_id)
                        DO UPDATE SET quantity = user_inventory.quantity + 1
                    """, winner.id, chosen_item_id)

                    # Get rarity text
                    weight = item_weights.get(chosen_item_id, 25)
                    if weight <= 10:
                        rarity_text = "🌟 VERY RARE 🌟"
                    elif weight <= 20:
                        rarity_text = "✨ RARE ✨"
                    elif weight <= 30:
                        rarity_text = "🔹 UNCOMMON 🔹"
                    else:
                        rarity_text = "COMMON"

                    await message.channel.send(f"{success_message} You won a **{chosen_item['name']}** ({rarity_text}) and **{coin_reward} PP coins**! 💰")
        except Exception as e:
            print(f"Error awarding game item: {e}")
            await message.channel.send(f"{success_message} (Error giving rewards)")

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
        """Handle answers for trivia, scramble, highlow, and math games"""
        if message.author.bot:
            return

        # Handle Word Scramble
        if self.current_scramble and message.channel.id == self.current_scramble['channel'].id:
            if message.author.id not in self.current_scramble['answered_users']:
                user_answer = message.content.strip().lower()
                if user_answer == self.current_scramble['word']:
                    self.current_scramble['answered_users'].add(message.author.id)
                    winner = message.author
                    correct_word = self.current_scramble['word']
                    self.current_scramble = None

                    # Award item
                    await self._award_game_item(winner, message, f"🎉 Correct, {winner.mention}! The word was **{correct_word.upper()}**!")
                    return

        # Handle Higher/Lower
        if self.current_highlow and message.channel.id == self.current_highlow['channel'].id:
            if message.author.id not in self.current_highlow['answered_users']:
                user_answer = message.content.strip().lower()
                if user_answer in ['h', 'higher', 'l', 'lower']:
                    self.current_highlow['answered_users'].add(message.author.id)
                    current = self.current_highlow['current_number']
                    next_num = self.current_highlow['next_number']
                    guess_higher = user_answer in ['h', 'higher']

                    is_correct = (next_num > current and guess_higher) or (next_num < current and not guess_higher) or (next_num == current)

                    if is_correct:
                        winner = message.author
                        self.current_highlow = None
                        result_msg = f"🎉 Correct, {winner.mention}! The next number was **{next_num}**!"
                        await self._award_game_item(winner, message, result_msg)
                    else:
                        await message.reply(f"❌ Wrong! The next number was **{next_num}**. Better luck next time!", delete_after=10)
                        # Don't clear the game, let others try
                    return

        # Handle Math Rush
        if self.current_math and message.channel.id == self.current_math['channel'].id:
            if message.author.id not in self.current_math['answered_users']:
                try:
                    user_answer = int(message.content.strip())
                    if user_answer == self.current_math['answer']:
                        self.current_math['answered_users'].add(message.author.id)
                        winner = message.author
                        problem = self.current_math['problem']
                        answer = self.current_math['answer']
                        self.current_math = None

                        await self._award_game_item(winner, message, f"🎉 Correct, {winner.mention}! **{problem} = {answer}**!")
                        return
                except ValueError:
                    pass  # Not a number, ignore

        # Handle Trivia
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
            channel = self.current_trivia_question['channel']
            profile_cog = self.bot.get_cog('PPProfile') # Get profile cog
            self.current_trivia_question = None
            
            # Set cooldown time when someone answers correctly
            guild_id = message.guild.id
            if hasattr(self, '_last_trivia_time'):  # Ensure dict exists
                self._last_trivia_time[guild_id] = datetime.now(timezone.utc)

            # Award a random item with varying rarity
            db = await self._get_db()
            try:
                async with db.acquire() as conn:
                    async with conn.transaction(): # Ensure atomicity for stats and rewards
                        # 1. Update Trivia Wins Stat
                        new_stats = await conn.fetchrow("""
                            INSERT INTO user_stats (user_id, trivia_wins) VALUES ($1, 1)
                            ON CONFLICT (user_id) DO UPDATE SET
                                trivia_wins = user_stats.trivia_wins + 1
                            RETURNING trivia_wins
                            """, winner.id)
                        new_trivia_wins = new_stats['trivia_wins'] if new_stats else 1
                        print(f"[Stats] Updated trivia_wins for {winner.name} ({winner.id}) to {new_trivia_wins}")

                        # 2. Check for Trivia Achievements
                        if profile_cog:
                            ctx = await self.bot.get_context(message) # Get context for achievement message
                            if new_trivia_wins == 1:
                                await profile_cog._grant_achievement(winner, 'first_win_trivia', ctx)
                            if new_trivia_wins == 10:
                                await profile_cog._grant_achievement(winner, 'ten_wins_trivia', ctx)

                        # 3. Award PP coins
                        coin_reward = 10
                        await conn.execute("""
                            INSERT INTO user_data (user_id, pp_coins) VALUES ($1, $2)
                            ON CONFLICT (user_id) DO UPDATE SET pp_coins = user_data.pp_coins + $2
                        """, winner.id, coin_reward)
                        print(f"[Trivia Reward] Awarded {coin_reward} PP coins to user {winner.id}")

                        # 4. Give Item Reward (Existing Logic)
                        # Get all available items
                        items = await conn.fetch("SELECT item_id, name FROM items")
                        if not items:
                            raise ValueError("No items found in database")

                        # Define item rarities (item_id: weight)
                        # Lower weight = more rare
                        item_weights = {
                            1: 40,  # Growth Potion - common
                            2: 30,  # Shrink Ray - uncommon
                            3: 20,  # Lucky Socks - rare
                            4: 10   # Reroll Token - very rare
                        }

                        # Get all item IDs and their corresponding weights
                        item_ids = [item['item_id'] for item in items]
                        weights = [item_weights.get(item_id, 25) for item_id in item_ids]  # Default weight 25 for any new items

                        # Choose a random item based on weights
                        chosen_item_id = random.choices(item_ids, weights=weights, k=1)[0]
                        chosen_item = next(item for item in items if item['item_id'] == chosen_item_id)

                        # Add the item to the user's inventory
                        await conn.execute("""
                            INSERT INTO user_inventory (user_id, item_id, quantity)
                            VALUES ($1, $2, 1)
                            ON CONFLICT (user_id, item_id)
                            DO UPDATE SET quantity = user_inventory.quantity + 1
                        """, winner.id, chosen_item_id)

                        # Get rarity text based on weight
                        weight = item_weights.get(chosen_item_id, 25)
                        if weight <= 10:
                            rarity_text = "🌟 VERY RARE 🌟"
                        elif weight <= 20:
                            rarity_text = "✨ RARE ✨"
                        elif weight <= 30:
                            rarity_text = "🔹 UNCOMMON 🔹"
                        else:
                            rarity_text = "COMMON"

                        await message.channel.send(
                            f"🎉 Correct, {winner.mention}! The answer was **{correct_answer}**. "
                            f"You won a **{chosen_item['name']}** ({rarity_text}) and **{coin_reward} PP coins**! 💰"
                        )
            except Exception as e:
                print(f"Error giving trivia reward: {e}")
                # Send a simplified message if reward fails
                try:
                    await channel.send(f"🎉 Correct, {winner.mention}! The answer was: **{correct_answer}** (Error giving item reward or updating stats)")
                except (discord.NotFound, discord.Forbidden) as send_e:
                    print(f"Error sending trivia correct message after reward failure: {send_e}")
        else:
            await message.reply(
                f"❌ Incorrect, {message.author.mention}! That's not the right answer. "
                "Try again next time!",
                delete_after=10
            )

async def setup(bot):
    await bot.add_cog(PPMinigames(bot))
    print("✅ PPMinigames Cog loaded")
