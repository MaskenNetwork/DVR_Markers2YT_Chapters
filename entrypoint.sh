#!/bin/sh

touch /app/data/bot.db
touch /app/data/bot.log

if [ ! -s /app/data/.env ]; then
    if [ -f /app/.env.template ]; then
        cp /app/.env.template /app/data/.env
    else
        touch /app/data/.env
    fi
fi

# Create symlinks to the files in /app/data/
ln -sf /app/data/bot.db /app/bot.db
ln -sf /app/data/bot.log /app/bot.log
ln -sf /app/data/.env /app/.env

exec "$@"