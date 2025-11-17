import json
import sqlite3
from .config import config

DB_PATH = config.db_path

# ============================================================================
# Custom Tools for Profile Storage
# ============================================================================

def save_profile_tool(tool_context, user_profile: dict) -> dict:
    """
    Save or update a user's matchmaking profile with validation and database persistence.

    This tool stores a user's profile into the matchmaking SQLite database
    (`db/matchmaking_data.db`). If a profile with the same `user_id` already exists,
    it is updated. The tool also updates the in-memory tool_context.state so
    downstream agents can detect that the profile is complete and ready for matching.

    -----------------------------------------------------------------------
    INPUT
    -----------------------------------------------------------------------
    tool_context : object
        A context object containing:
            - state: a mutable dictionary used to track workflow state.
              Must contain or eventually store `state["user_id"]`.

    user_profile : dict
        A dictionary of user attributes. The tool validates required fields and
        converts/normalizes some values before saving.

        REQUIRED FIELDS:
            user_id : str | int
                If missing from user_profile, the tool attempts to read it from
                tool_context.state["user_id"]. If still missing → returns error.

            name : str
            age : int or str convertible to int (must be >= 18)
            gender : str
            sexual_orientation : str

        REQUIRED PREFERENCES (either inside `preferences` dict or individual fields):
            preferences : dict (recommended)
                {
                  "looking_for": str,
                  "age_range": str or list,
                  "relationship_type": str (optional)
                }
            If `preferences` is missing or not a dict, the tool attempts to construct it
            from:
                - looking_for
                - age_range
                - relationship_type

            Missing `looking_for` or `age_range` → returns error.

        OPTIONAL FIELDS:
            hobbies : list[str]
            personality_traits : list[str]
            bio : str
            tool_context : dict  (stored as JSON)
            any other auxiliary profile metadata is allowed but not required.

    -----------------------------------------------------------------------
    PROCESSING & VALIDATION
    -----------------------------------------------------------------------
    1. Resolves user_id from input or tool_context.state.
    2. Validates:
         - user_id exists
         - age is a valid integer >= 18
         - required fields are present
         - preferences contain required keys
    3. Serializes `preferences`, `hobbies`, `personality_traits`, and `tool_context`
       into JSON.
    4. Executes an UPSERT into SQLite:
         - INSERT if new user_id
         - UPDATE if user_id already exists
    5. Updates tool_context.state:
         - state["ready_for_matching"] = True
         - state["profile_saved_or_updated"] = True
         - state["all_profiles"][user_id] = user_profile

    -----------------------------------------------------------------------
    OUTPUT (dict)
    -----------------------------------------------------------------------
    On success:
        {
            "status": "success",
            "profile_saved_or_updated": True,
            "ready_for_matching": True,
            "message": "Profile for user saved successfully, user is now ready to find matches, continue with what is instructed to you for the next step.",
            "data": user_profile
        }

    On error (missing fields, invalid age, missing preferences, etc.):
        {
            "status": "error",
            "message": "<error description>",
            "data": user_profile
        }

    -----------------------------------------------------------------------
    NOTES FOR AGENTS
    -----------------------------------------------------------------------
    - Always supply at least the required fields.
    - If you don't include preferences as a dict, the tool will attempt to
      build one from the flat fields (looking_for, age_range, relationship_type).
    - The tool sets `ready_for_matching=True`; downstream agents can rely on this.
    - The tool is idempotent for a given user_id due to SQLite UPSERT behavior.
    """

    state = tool_context.state

    # Get user_id
    user_id = user_profile.get("user_id") or state.get("user_id")
    print(f"save_profile_tool's user_id: {user_id}")
    if not user_id:
        return {"status": "error", "message": "Missing user_id. Cannot save profile.", "data": user_profile}

    # Age validation
    age = user_profile.get("age")
    try:
        age = int(age)
    except (TypeError, ValueError):
        age = None

    if age is not None and age < 18:
        return {"status": "error", "message": "User is under 18. Profile cannot be saved.", "data": user_profile}

    # FIX: More flexible field validation - check what's actually needed
    required_fields = ["name", "age", "gender", "sexual_orientation"]
    missing = [f for f in required_fields if f not in user_profile or user_profile[f] is None]
    if missing:
        return {"status": "error", "message": f"Missing required fields: {', '.join(missing)}", "data": user_profile}

    # FIX: Handle preferences as dict properly
    preferences = user_profile.get("preferences", {})
    if not isinstance(preferences, dict):
        # Try to construct from collected info
        preferences = {
            "looking_for": user_profile.get("looking_for", ""),
            "age_range": user_profile.get("age_range", ""),
            "relationship_type": user_profile.get("relationship_type", "")
        }
    
    # Ensure preferences have the required keys
    if not preferences.get("looking_for") or not preferences.get("age_range"):
        return {
            "status": "error", 
            "message": "Missing preferences: looking_for and age_range are required",
            "data": user_profile
        }

    # Serialize fields
    preferences_json = json.dumps(preferences)
    hobbies_json = json.dumps(user_profile.get("hobbies", []))
    personality_traits_json = json.dumps(user_profile.get("personality_traits", []))
    tool_context_json = json.dumps(user_profile.get("tool_context", {}))

    # Save to database
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_profiles (
                user_id, name, age, gender, sexual_orientation,
                preferences, hobbies, personality_traits, bio,
                tool_context, create_time, update_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                age = excluded.age,
                gender = excluded.gender,
                sexual_orientation = excluded.sexual_orientation,
                preferences = excluded.preferences,
                hobbies = excluded.hobbies,
                personality_traits = excluded.personality_traits,
                bio = excluded.bio,
                tool_context = excluded.tool_context,
                update_time = CURRENT_TIMESTAMP
        """, (
            user_id,
            user_profile.get("name"),
            age,
            user_profile.get("gender"),
            user_profile.get("sexual_orientation"),
            preferences_json,
            hobbies_json,
            personality_traits_json,
            user_profile.get("bio", ""),
            tool_context_json
        ))
        conn.commit()
        state["ready_for_matching"] = True
        state["profile_saved_or_updated"] = True
    # Update in-memory state
    state.setdefault("all_profiles", {})[user_id] = user_profile

    #return {"status": "success", "profile_saved_or_updated": True, "ready_for_matching": True, "message": f"Profile for user saved successfully, user is now ready to find matches, continue with what is instructed to you for the next step.", "data": user_profile}
    return {"status": "success"}

def request_match_confirmation_tool(tool_context) -> dict:
    """
    Mark that the user explicitly confirms they want to begin the matching process.

    This tool updates the matchmaking workflow state to signal that the user
    is ready to proceed to the matchmaking phase. It does not validate or modify
    the user's profile — it only sets the readiness flag inside tool_context.state.

    -----------------------------------------------------------------------
    INPUT
    -----------------------------------------------------------------------
    tool_context : object
        A context object containing:
            - state: a mutable dictionary shared between tools and agents.

        No additional fields are required. This tool does NOT require a user_id
        or any profile data.

    -----------------------------------------------------------------------
    PROCESSING
    -----------------------------------------------------------------------
    1. Sets:
         state["ready_for_matching"] = True
       to indicate that the user has explicitly confirmed they want matches.
    2. Performs no database actions.
    3. Performs no profile validation.

    -----------------------------------------------------------------------
    OUTPUT (dict)
    -----------------------------------------------------------------------
    Always returns a confirmation dictionary:

        {
            "status": "confirmed",
            "ready_for_matching": True,
            "message": "User is ready to find matches! Now transfer the user to the match making agent."
        }

    -----------------------------------------------------------------------
    NOTES FOR AGENTS
    -----------------------------------------------------------------------
    - Call this when the user verbally confirms or indicates they want to start
      finding matches.
    - It is safe and idempotent — calling multiple times simply reaffirms readiness.
    - After this tool is called, agents should transfer control to the matchmaking agent.
    """
    state = tool_context.state
    state["ready_for_matching"] = True
    return {"status": "confirmed", "ready_for_matching": True, "message": "User is ready to find matches! Now transfer the user to the match making agent."}


def request_message_confirmation_tool(match_name: str, tool_context) -> dict:
    """
    Indicate that the user wants to begin messaging a specific match.

    This tool sets the internal workflow state so downstream agents know which
    match the user intends to contact. It does not generate the message itself —
    it simply records the chosen match and signals that the next step is to help
    the user draft or send a message.

    -----------------------------------------------------------------------
    INPUT
    -----------------------------------------------------------------------
    match_name : str
        The name or identifier of the match the user wants to message.
        Must be provided; no default exists.

    tool_context : object
        A context object containing:
            - state: a mutable dictionary shared between tools and agents.
        No additional profile fields are required.

    -----------------------------------------------------------------------
    PROCESSING
    -----------------------------------------------------------------------
    1. Stores the selected match name:
         state["messaging_match"] = match_name
    2. Does not validate the match existence.
    3. Does not perform database actions.

    -----------------------------------------------------------------------
    OUTPUT (dict)
    -----------------------------------------------------------------------
    Always returns a confirmation dictionary with the match name embedded:

        {
            "status": "confirmed",
            "message": "User is ready to draft message for <match_name>! Now help the user!"
        }

    -----------------------------------------------------------------------
    NOTES FOR AGENTS
    -----------------------------------------------------------------------
    - Call this tool when the user says they want to message a specific match.
    - After calling, agents should transition into a message-drafting flow.
    - The stored value in state["messaging_match"] indicates the current target.
    - The tool is idempotent: calling again will simply overwrite the target match.
    """

    state = tool_context.state
    state["messaging_match"] = match_name
    return {"status": "confirmed", "message": f"User is ready to draft message for {match_name}! Now help the user!"}


def get_all_profiles_tool(tool_context) -> dict:
    """
    Retrieve all stored user profiles from the matchmaking database, excluding
    the current user.

    This tool loads all profiles from the SQLite database, automatically parses
    JSON-encoded fields, and returns a dictionary of user profiles keyed by
    user_id. The currently active user is removed from the returned results to
    support match searching.

    -----------------------------------------------------------------------
    INPUT
    -----------------------------------------------------------------------
    tool_context : object
        A context object containing:
            - state: a mutable dictionary shared between tools and agents.
              Must contain:
                  state["user_id"] : str | int
                      Used to filter out the requesting user.
              If missing, the tool will simply return all profiles.

    -----------------------------------------------------------------------
    PROCESSING
    -----------------------------------------------------------------------
    1. Reads `state["user_id"]` to determine which profile to exclude.
    2. Connects to the SQLite database at DB_PATH and executes:
         SELECT * FROM user_profiles
    3. Converts each row into a dictionary, using column names for keys.
    4. Automatically deserializes the following JSON fields:
         - preferences
         - hobbies
         - personality_traits
    5. Builds a dictionary:
         { user_id : profile_dict }
    6. Removes the current user’s profile from the results.

    -----------------------------------------------------------------------
    OUTPUT (dict)
    -----------------------------------------------------------------------
    On success:
        {
            "status": "success",
            "profiles": {
                <user_id_1>: { ... full profile ... },
                <user_id_2>: { ... },
                ...
            },
            "count": <number_of_profiles_excluding_current_user>
        }

    -----------------------------------------------------------------------
    NOTES FOR AGENTS
    -----------------------------------------------------------------------
    - Use this tool to retrieve candidate profiles for matchmaking.
    - Profiles returned include all fields: demographics, preferences,
      hobbies, personality traits, and bio.
    - The tool does *not* perform ranking, filtering, or matching logic.
    - Agents may safely call this multiple times; results reflect the live DB.
    - Ensure that the matchmaking agent interprets JSON-decoded fields properly.

    """

    state = tool_context.state
    current_user_id = state.get("user_id")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_profiles")
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
    
    profiles = {}
    for row in rows:
        record = dict(zip(col_names, row))
        record["preferences"] = json.loads(record.get("preferences") or "{}")
        record["hobbies"] = json.loads(record.get("hobbies") or "[]")
        record["personality_traits"] = json.loads(record.get("personality_traits") or "[]")
        profiles[record["user_id"]] = record
    
    other_profiles = {uid: p for uid, p in profiles.items() if uid != current_user_id}
    
    return {"status": "success", "profiles": other_profiles, "count": len(other_profiles)}


def get_profile_by_id_tool(tool_context) -> dict:
    """
    Retrieve the full profile of the current user from the matchmaking database.

    This tool reads the active user's ID from tool_context.state and loads their
    corresponding profile record from the SQLite database. JSON-encoded fields
    are automatically parsed before returning the profile.

    -----------------------------------------------------------------------
    INPUT
    -----------------------------------------------------------------------
    tool_context : object
        A context object containing:
            - state: a mutable dictionary shared between tools and agents.
              Must contain:
                  state["user_id"] : str | int
                      The ID of the user whose profile should be retrieved.

        No additional arguments are required.

    -----------------------------------------------------------------------
    PROCESSING
    -----------------------------------------------------------------------
    1. Reads the value of state["user_id"].
       - If this is missing or None, the database query will return no result.
    2. Connects to SQLite at DB_PATH and executes:
         SELECT * FROM user_profiles WHERE user_id = ?
    3. If a matching row is found:
         - Converts the row into a dictionary based on DB column names.
         - Deserializes JSON fields:
               preferences
               hobbies
               personality_traits
    4. Returns the structured profile.
    5. If no matching profile exists, returns an error.

    -----------------------------------------------------------------------
    OUTPUT (dict)
    -----------------------------------------------------------------------
    On success:
        {
            "status": "success",
            "profile": {
                "user_id": ...,
                "name": ...,
                "age": ...,
                "gender": ...,
                "sexual_orientation": ...,
                "preferences": { ... },
                "hobbies": [ ... ],
                "personality_traits": [ ... ],
                "bio": ...,
                "tool_context": ...,
                "create_time": ...,
                "update_time": ...
            }
        }

    On failure (no record found):
        {
            "status": "error",
            "message": "Profile '<user_id>' not found"
        }

    -----------------------------------------------------------------------
    NOTES FOR AGENTS
    -----------------------------------------------------------------------
    - Use this tool to verify whether a profile is complete or to retrieve
      the user's latest saved information.
    - The tool does not modify any data; it only reads from the database.
    - JSON fields are already parsed into Python objects — no extra handling needed.
    - For accessing other users' profiles, use get_all_profiles_tool instead.
    """

    state = tool_context.state
    current_user_id = state.get("user_id")

    """Retrieve a specific user profile by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_profiles WHERE user_id = ?", (current_user_id,))
        row = cursor.fetchone()
        if row:
            col_names = [desc[0] for desc in cursor.description]
            record = dict(zip(col_names, row))
            record["preferences"] = json.loads(record.get("preferences") or "{}")
            record["hobbies"] = json.loads(record.get("hobbies") or "[]")
            record["personality_traits"] = json.loads(record.get("personality_traits") or "[]")
            return {"status": "success", "profile": record}
    
    return {"status": "error", "message": f"Profile '{current_user_id}' not found"}

