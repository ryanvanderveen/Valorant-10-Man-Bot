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
                        last_used TIMESTAMP DEFAULT NULL
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

                # Populate items table if empty
                item_count = await conn.fetchval("SELECT COUNT(*) FROM items")
                if item_count == 0:
                    print(" Populating 'items' table with initial data...")
                    initial_items = [
                        ('Growth Potion', 'Temporarily increases your next pp roll.', 'pp_boost', 2, 60, True),
                        ('Shrink Ray', 'Temporarily decreases your next pp roll. Risky!', 'pp_boost', -2, 60, True),
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
