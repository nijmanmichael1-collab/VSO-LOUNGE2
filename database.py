import sqlite3
import datetime

DB_NAME = "data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table for Roblox linked accounts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS linked_roblox (
            discord_id INTEGER PRIMARY KEY,
            roblox_username TEXT,
            roblox_id INTEGER
        )
    ''')
    
    # Table to track weekly recommendations limit per user
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommend_limits (
            discord_id INTEGER,
            week_number INTEGER,
            year INTEGER,
            count INTEGER,
            PRIMARY KEY (discord_id, week_number, year)
        )
    ''')
    
    # Table to track cooldown timestamps for /recommend
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommend_cooldowns (
            discord_id INTEGER PRIMARY KEY,
            last_used_timestamp REAL
        )
    ''')
    
    # Table to track active recommendations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            recommended_id INTEGER PRIMARY KEY,
            recommender_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            roblox_username TEXT,
            roblox_id INTEGER,
            reason TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Roblox Linking Helpers ---
def link_roblox_user(discord_id: int, roblox_username: str, roblox_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO linked_roblox (discord_id, roblox_username, roblox_id)
        VALUES (?, ?, ?)
    ''', (discord_id, roblox_username, roblox_id))
    conn.commit()
    conn.close()

def get_roblox_data(discord_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT roblox_username, roblox_id FROM linked_roblox WHERE discord_id = ?', (discord_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# --- Cooldown Helpers ---
def get_cooldown_remaining(discord_id: int) -> float:
    """Returns remaining cooldown seconds if user is on 2-minute cooldown, else 0."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT last_used_timestamp FROM recommend_cooldowns WHERE discord_id = ?', (discord_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        return 0.0
        
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    elapsed = now - row[0]
    cooldown_time = 120.0  # 2 minutes = 120 seconds
    
    if elapsed < cooldown_time:
        return cooldown_time - elapsed
    return 0.0

def update_cooldown(discord_id: int):
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO recommend_cooldowns (discord_id, last_used_timestamp)
        VALUES (?, ?)
    ''', (discord_id, now))
    conn.commit()
    conn.close()

# --- Weekly Limit Helpers ---
def can_recommend(discord_id: int) -> bool:
    now = datetime.datetime.now(datetime.timezone.utc)
    year, week, _ = now.isocalendar()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT count FROM recommend_limits 
        WHERE discord_id = ? AND week_number = ? AND year = ?
    ''', (discord_id, week, year))
    row = cursor.fetchone()
    conn.close()
    
    if row is None or row[0] < 5:
        return True
    return False

def add_recommend_count(discord_id: int):
    now = datetime.datetime.now(datetime.timezone.utc)
    year, week, _ = now.isocalendar()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO recommend_limits (discord_id, week_number, year, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(discord_id, week_number, year) 
        DO UPDATE SET count = count + 1
    ''', (discord_id, week, year))
    conn.commit()
    conn.close()

# --- Recommendation Tracking Helpers ---
def save_recommendation(recommended_id: int, recommender_id: int, channel_id: int, message_id: int, rblx_user: str, rblx_id: int, reason: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO recommendations 
        (recommended_id, recommender_id, channel_id, message_id, roblox_username, roblox_id, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (recommended_id, recommender_id, channel_id, message_id, rblx_user, rblx_id, reason))
    conn.commit()
    conn.close()

def get_recommendation(recommended_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT recommender_id, channel_id, message_id, roblox_username, roblox_id, reason 
        FROM recommendations WHERE recommended_id = ?
    ''', (recommended_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def delete_recommendation(recommended_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recommendations WHERE recommended_id = ?', (recommended_id,))
    conn.commit()
    conn.close()
