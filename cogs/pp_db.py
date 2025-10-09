import os
import asyncpg
import discord
from discord.ext import commands

class PPDB(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DATABASE_URL = os.getenv("DATABASE_URL")
        self.db = None
        self.bot.loop.create_task(self.initialize_db())

    async def initialize_db(self):
        """Creates database connection pool and ensures all required tables exist."""
        if not self.DATABASE_URL:
            print(" ERROR: DATABASE_URL is not set! Check your environment variables.")
            return

        # Fix asyncpg issue: Convert postgresql:// → postgres://
        if self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgres://", 1)

        try:
            self.db = await asyncpg.create_pool(self.DATABASE_URL)
            print(" Successfully connected to PostgreSQL!")

            async with self.db.acquire() as conn:
                # Ensure pp_sizes table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS pp_sizes (
                        user_id BIGINT PRIMARY KEY,
                        size INTEGER,
                        last_roll_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NULL
                    )
                """)
                print(" Table 'pp_sizes' checked/created.")

                # Ensure items table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        item_id SERIAL PRIMARY KEY,
                        name VARCHAR(50) UNIQUE NOT NULL,
                        description VARCHAR(255),
                        effect_type VARCHAR(50),
                        effect_value INTEGER,
                        duration_minutes INTEGER DEFAULT 0,
                        usable BOOLEAN DEFAULT TRUE
                    )
                """)
                print(" Table 'items' checked/created.")

                # Ensure user_inventory table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_inventory (
                        user_id BIGINT NOT NULL,
                        item_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (user_id, item_id),
                        FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                    )
                """)
                print(" Table 'user_inventory' checked/created.")

                # Ensure user_active_effects table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_active_effects (
                        user_id BIGINT NOT NULL,
                        effect_type VARCHAR(50) NOT NULL,
                        effect_value INTEGER,
                        end_time TIMESTAMP NOT NULL,
                        PRIMARY KEY (user_id, effect_type)
                    )
                """)
                print(" Table 'user_active_effects' checked/created.")

                # Ensure user_stats table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_stats (
                        user_id BIGINT PRIMARY KEY,
                        total_rolls INTEGER DEFAULT 0,
                        zero_rolls INTEGER DEFAULT 0,
                        twenty_rolls INTEGER DEFAULT 0,
                        duel_wins INTEGER DEFAULT 0,
                        trivia_wins INTEGER DEFAULT 0,
                        days_as_hog_daddy INTEGER DEFAULT 0
                    )
                """)
                print(" Table 'user_stats' checked/created.")

                # Ensure achievements table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS achievements (
                        achievement_id VARCHAR(50) PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        description VARCHAR(255),
                        reward_role_name VARCHAR(100)
                    )
                """)
                print(" Table 'achievements' checked/created.")

                # Ensure user_achievements table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_achievements (
                        user_id BIGINT NOT NULL,
                        achievement_id VARCHAR(50) NOT NULL,
                        earned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (user_id, achievement_id),
                        FOREIGN KEY (achievement_id) REFERENCES achievements(achievement_id) ON DELETE CASCADE
                    )
                """)
                print(" Table 'user_achievements' checked/created.")

                # Populate achievements table if empty
                achievement_count = await conn.fetchval("SELECT COUNT(*) FROM achievements")
                if achievement_count == 0:
                    print(" Populating 'achievements' table with initial data...")
                    initial_achievements = [
                        ('roll_a_zero', 'Micro PP', 'Rolled a 0 for the first time', None),
                        ('roll_a_twenty', 'Maximum PP', 'Rolled a 20 for the first time', None),
                        ('became_hog_daddy', 'Hog Daddy', 'Became the Daily Hog Daddy', None),
                        ('first_duel_win', 'Duelist', 'Won your first PP duel', None),
                        ('ten_duel_wins', 'Duel Master', 'Won 10 PP duels', None),
                        ('first_win_trivia', 'Trivia Novice', 'Won your first trivia game', None),
                        ('ten_wins_trivia', 'Trivia Master', 'Won 10 trivia games', None),
                    ]
                    await conn.executemany("""
                        INSERT INTO achievements (achievement_id, name, description, reward_role_name)
                        VALUES ($1, $2, $3, $4)
                    """, initial_achievements)
                    print(f" Added {len(initial_achievements)} initial achievements.")

                # Populate items table if empty
                item_count = await conn.fetchval("SELECT COUNT(*) FROM items")
                if item_count == 0:
                    print(" Populating 'items' table with initial data...")
                    initial_items = [
                        ('Growth Potion', 'Temporarily increases your next pp roll.', 'pp_boost', 2, 60, True),
                        ('Shrink Ray', 'Zap another user to shrink their pp by 2 inches! Use: pls use shrink ray @user', 'shrink_ray', -2, 0, True),
                        ('Lucky Socks', 'Slightly increases chance of a larger roll next time.', 'luck_boost', 1, 0, True),
                        ('Reroll Token', 'Grants one reroll on your next pp command.', 'reroll', 1, 0, True),
                    ]
                    await conn.executemany("""
                        INSERT INTO items (name, description, effect_type, effect_value, duration_minutes, usable)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, initial_items)
                    print(f" Added {len(initial_items)} initial items.")

            print(" PostgreSQL database initialization complete!")

        except Exception as e:
            print(f" ERROR: Unable to connect to PostgreSQL: {e}")
            exit(1)

    async def get_db(self):
        """Get the database pool. Ensures it's initialized first."""
        if not self.db:
            await self.initialize_db()
        return self.db

async def setup(bot):
    await bot.add_cog(PPDB(bot))
    print("✅ PPDB Cog loaded")
