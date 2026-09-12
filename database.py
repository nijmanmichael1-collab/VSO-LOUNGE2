import sqlite3

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            roblox_username TEXT,
            roblox_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

def save_user(discord_id: int, roblox_username: str, roblox_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (discord_id, roblox_username, roblox_id)
        VALUES (?, ?, ?)
    """, (discord_id, roblox_username, roblox_id))
    conn.commit()
    conn.close()

def get_user(discord_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT roblox_username, roblox_id FROM users WHERE discord_id = ?", (discord_id,))
    result = cursor.fetchone()
    conn.close()
    return result # Returns (roblox_username, roblox_id) or None
