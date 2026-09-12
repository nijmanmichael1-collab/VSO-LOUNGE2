import sqlite3
import time

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
    
    # Recommendations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            recommended_id INTEGER PRIMARY KEY,
            message_id INTEGER
        )
    """)
    
    # Limits table to track weekly recommendation count per recommender
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendation_limits (
            recommender_id INTEGER PRIMARY KEY,
            count INTEGER,
            reset_timestamp REAL
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

def check_and_update_limit(recommender_id: int, max_limit: int = 5) -> tuple[bool, str]:
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    now = time.time()
    one_week_seconds = 7 * 24 * 60 * 60

    cursor.execute("SELECT count, reset_timestamp FROM recommendation_limits WHERE recommender_id = ?", (recommender_id,))
    row = cursor.fetchone()

    if row is None or now >= row[1]:
        new_reset = now + one_week_seconds
        cursor.execute("""
            INSERT OR REPLACE INTO recommendation_limits (recommender_id, count, reset_timestamp)
            VALUES (?, ?, ?)
        """, (recommender_id, 1, new_reset))
        conn.commit()
        conn.close()
        return True, ""
    else:
        current_count, reset_timestamp = row
        if current_count >= max_limit:
            conn.close()
            remaining_hours = int((reset_timestamp - now) // 3600)
            return False, f"You have reached your limit of 5 recommendations per week. Try again in ~{remaining_hours} hours."
        
        cursor.execute("""
            UPDATE recommendation_limits SET count = count + 1 WHERE recommender_id = ?
        """, (recommender_id,))
        conn.commit()
        conn.close()
        return True, ""
