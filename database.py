import sqlite3

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            roblox_username TEXT,
            roblox_id INTEGER
        )
    """)
    
    # Recommendations table (stores the latest message ID sent to channel)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            recommended_id INTEGER PRIMARY KEY,
            message_id INTEGER
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
    return result

def save_recommendation(recommended_id: int, message_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO recommendations (recommended_id, message_id)
        VALUES (?, ?)
    """, (recommended_id, message_id))
    conn.commit()
    conn.close()

def get_recommendation(recommended_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT message_id FROM recommendations WHERE recommended_id = ?", (recommended_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None
