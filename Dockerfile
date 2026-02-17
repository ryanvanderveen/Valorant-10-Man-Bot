services:
  db:
    image: postgres:15-alpine
    container_name: discord-bot-db
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: railway
    volumes:
      - /opt/appdata/discord-bot/db:/var/lib/postgresql/data
    restart: unless-stopped

  discord-bot:
    build: 
      context: https://github.com/ryanvanderveen/Valorant-10-Man-Bot.git
      dockerfile_inline: |
        FROM python:3.11-slim
        WORKDIR /app
        # Install system dependencies for Python packages
        RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
        # Install Python dependencies from your repo
        COPY requirements.txt .
        RUN pip install --no-cache-dir -r requirements.txt
        # Copy the rest of your bot code
        COPY . .
        # Start the bot using main.py
        CMD ["python", "main.py"]
    container_name: discord-bot-app
    depends_on:
      - db
    environment:
      - DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/railway
      - DISCORD_TOKEN=${DISCORD_TOKEN}
    restart: unless-stopped
