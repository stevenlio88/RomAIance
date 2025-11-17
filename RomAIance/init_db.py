import json
import sqlite3
from .config import config

# ============================================================================
# Sample User Data for Testing
# ============================================================================

def initialize_sqlite_schema(db_path: str):
    """
    Create the required SQLite tables and triggers for the matchmaking app.

    This function sets up three tables if they do not exist:
        - events: stores logs of actions, tool invocations, errors, and metadata.
        - sessions: stores session state, creation, and update timestamps.
        - user_profiles: stores user profiles with JSON-encoded fields 
          (preferences, hobbies, personality traits, tool_context).

    Triggers are created to automatically update the `update_time` field in
    sessions and user_profiles whenever a row is updated.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file. Defaults to "matchmaking_data.db".

    Returns
    -------
    None
        Prints a confirmation message when schema initialization is complete.
    """

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            app_name TEXT NOT NULL,
            user_id TEXT,
            session_id TEXT,
            invocation_id TEXT,
            author TEXT,
            actions TEXT,
            long_running_tool_ids_json TEXT,
            branch TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            content TEXT,
            grounding_metadata TEXT,
            custom_metadata TEXT,
            usage_metadata TEXT,
            citation_metadata TEXT,
            partial BOOLEAN,
            turn_complete BOOLEAN,
            error_code TEXT,
            error_message TEXT,
            interrupted BOOLEAN
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            app_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            state TEXT,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            age INTEGER,
            gender TEXT,
            sexual_orientation TEXT,
            preferences TEXT,
            hobbies TEXT,
            personality_traits TEXT,
            bio TEXT,
            tool_context TEXT,
            create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        conn.commit()
    
    print(f"SQLite schema initialized at: {db_path}")

def insert_sample_users(db_path: str):
    """
    Insert predefined sample users into the user_profiles table for testing.

    Only inserts users that do not already exist in the database 
    (checked by user_id).

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file. Defaults to "matchmaking_data.db".

    Returns
    -------
    None
        Commits the inserted users to the database.
    """
    with open(config.sample_data) as f:
        SAMPLE_USERS = json.load(f)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for user in SAMPLE_USERS:
            cursor.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", (user["user_id"],))
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO user_profiles (
                        user_id, name, age, gender, sexual_orientation,
                        preferences, hobbies, personality_traits, bio, tool_context
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user["user_id"], user["name"], user["age"], user["gender"],
                    user["sexual_orientation"], json.dumps(user["preferences"]),
                    json.dumps(user["hobbies"]), json.dumps(user["personality_traits"]),
                    user["bio"], json.dumps({})
                ))
        conn.commit()