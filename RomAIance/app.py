# General imports
import asyncio
import uuid
import os

# Google ADK imports
from google.adk.sessions import DatabaseSessionService
from google.adk.runners import Runner
from google.genai import types

# Support imports for app
from .agent import root_agent
from .init_db import initialize_sqlite_schema, insert_sample_users
from .config import config

# ============================================================================
# Application Runner
# ============================================================================

class MatchmakingApp:
    def __init__(self):
        self.app_name = config.app_name
        self.model_to_use = config.model_to_use
        self.db_path = config.db_path
        self.user_id = f"user_{uuid.uuid4().hex[:8]}"

        # Initialize DB only if it doesn't exist
        if not os.path.exists(self.db_path):
            initialize_sqlite_schema(self.db_path)
            insert_sample_users(self.db_path)
            print(f"MatchmakingApp initialized with DB at: {self.db_path}")

        # Create the database URL for SQLAlchemy-style connection
        db_url = f"sqlite:///{self.db_path}"

        # Initialize services
        self.session_service = DatabaseSessionService(db_url=db_url)
        self.runner = Runner(
            agent=root_agent,
            app_name=self.app_name,
            session_service=self.session_service
        )

        print(f"\nMatchmakingApp connected with DB at: {self.db_path}")

    async def initialize_session(self, name, age, gender, orientation):
        """Create session with initial state."""
        session_id = str(uuid.uuid4())
        await self.session_service.create_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=session_id,
            state={
                "user_id": self.user_id,
                "user_name": name,
                "user_age": age,
                "user_gender": gender,
                "user_sexual_orientation": orientation,
                "ready_for_matching": False,
                "profile_saved_or_updated": False,
                "messaging_match": None,
                "all_profiles": {},
                "workflow_stage": "profile_building"
            }
        )
        return session_id
    
    async def send_message(self, message: str, session_id: str) -> tuple:
        """Send message and return (response_text, is_complete)."""
        query_content = types.Content(role="user", parts=[types.Part(text=message)])
        response_text = ""
        is_complete = False
        
        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=session_id,
            new_message=query_content
        ):
            #print(f"is_final_response: {event.is_final_response()}")
            if event.is_final_response():
                if event.content and event.content.parts:
                    text_parts = []
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                            # Check for session completion markers
                            lower_text = part.text.lower()
                            if any(p in lower_text for p in 
                                   ["good luck", "take care", "feel free to come back"]):
                                is_complete = True
                            # Check for underage exit
                            if "underage_exit" in lower_text or "at least 18" in lower_text:
                                is_complete = True
                    response_text = "\n".join(text_parts)
                break
        
        return response_text or "Working on it...", is_complete
    
    async def run(self):
        """Main conversation loop."""
        try:
            print("\n💘 Welcome to RomAIance! 💘")
            print("=" * 60)
            
            # Collect basic info - let LLM handle age interpretation (simulate account info setup)
            name = input("\nWhat's your name? ").strip()
            age = input("What's your age? ").strip()
            gender = input("What's your gender? ").strip()
            orientation = input("What's your sexual orientation? ").strip()
            
            # Create session with raw age input (LLM will interpret)
            session_id = await self.initialize_session(name, age, gender, orientation)
            print(f"Session created: {session_id}")
            print(f"User id: {self.user_id}")
            
            initial_msg = (
                f"Hi! My name is {name}, I'm {age} years old, {gender}, "
                f"and I'm interested in {orientation}. I'd like to create my dating profile."
            )
            
            print(f"\n{name}: {initial_msg}")
            response, is_complete = await self.send_message(initial_msg, session_id)
            print(f"\n Assistant: {response}")
            
            # Check if agent detected underage user
            if is_complete and ("underage_exit" in response.lower() or "at least 18" in response.lower()):
                print("\n" + "=" * 60)
                print("❌ Age restriction enforced - No data saved ❌")
                print("=" * 60)
                return
            
            # Main conversation loop
            while not is_complete:
                print("\n" + "-" * 60)
                user_input = input(f"\n{name}: ").strip()
                
                if user_input.lower() in ["exit", "quit", "bye"]:
                    print("\n👋 Thank you for RomAIance RomAIance! 💘")
                    break
                
                if not user_input:
                    continue
                
                response, is_complete = await self.send_message(user_input, session_id)
                
                # if (not response or response == "Working on it..."):
                #     print(f"\n Assistant: Processing your request...")
                #     await asyncio.sleep(0.5)
                #     continue
                
                print(f"\n Assistant: {response}")
                
                # Check for underage detection during conversation
                if is_complete and ("underage_exit" in response.lower() or "at least 18" in response.lower()):
                    print("\n" + "=" * 60)
                    print("❌ Age restriction enforced - No data saved ❌")
                    print("=" * 60)
                    break
            
            # Successful completion
            if is_complete and "underage_exit" not in response.lower() and "at least 18" not in response.lower():
                print("\n" + "=" * 60)
                print("✨ Session completed successfully! ✨")
                print("=" * 60)
                
        except KeyboardInterrupt:
            print("\n\n👋 Thank you for using RomAIance! 💘")
        except Exception as e:
            print(f"\n❌ Error: {e} ❌")
            import traceback
            traceback.print_exc()
        finally:
            await self.runner.close()

async def main():
    """Application entry point"""
    app = MatchmakingApp()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())