import os
import json
import re
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Thread pool for concurrent LLM calls
# Using a reasonable pool size to allow multiple sessions to generate concurrently
executor = ThreadPoolExecutor(max_workers=10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup: nothing special needed here, resources are already initialized
    yield
    # Shutdown: clean up resources
    print("Shutting down thread pool executor...")
    executor.shutdown(wait=True)


app = FastAPI(lifespan=lifespan)


# Session management
class SessionState:
    """Stores state for a single user session."""
    def __init__(self):
        self.conversation_history: List[Dict[str, str]] = []
        self.application_description: str = ""


# Dictionary to store session states by session ID
sessions: Dict[str, SessionState] = {}


def strip_markdown_code_blocks(text: str) -> str:
    """
    Remove markdown code block formatting (```html, ```, etc.) from the text.
    """
    # First strip any leading/trailing whitespace
    text = text.strip()

    # Remove opening code block tags like ```html, ```HTML, or just ```
    # Look for it at the very beginning of the string
    if text.startswith('```'):
        # Find the end of the first line
        first_newline = text.find('\n')
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            # If no newline, just remove the backticks and any following word
            text = re.sub(r'^```[a-zA-Z]*', '', text)

    # Remove closing code block tags
    # Look for it at the very end of the string
    if text.endswith('```'):
        # Find the start of the last line with backticks
        last_backticks = text.rfind('\n```')
        if last_backticks != -1:
            text = text[:last_backticks]
        else:
            # If backticks are on their own, just remove them
            text = text[:-3]

    return text.strip()


def _get_llm_response_sync(session: SessionState, user_message: str) -> str:
    """
    Synchronous function to send a message to the LLM and get the HTML response.
    This runs in a thread pool to avoid blocking the event loop.
    """
    # Add user message to history
    session.conversation_history.append({
        "role": "user",
        "content": user_message
    })

    try:
        # Call Anthropic API
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=session.conversation_history
        )

        # Extract the assistant's response
        assistant_message = response.content[0].text

        # Add assistant response to history
        session.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        # Strip markdown code blocks before returning
        cleaned_html = strip_markdown_code_blocks(assistant_message)
        return cleaned_html

    except Exception as e:
        print(f"Error calling Anthropic API: {e}")
        raise


async def get_llm_response(session: SessionState, user_message: str) -> str:
    """
    Async wrapper to send a message to the LLM and get the HTML response.
    Runs the synchronous API call in a thread pool for concurrent execution.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _get_llm_response_sync, session, user_message)


def create_initial_prompt(app_description: str) -> str:
    """
    Create the initial prompt for the LLM to generate the home screen.
    """
    return f"""You're an application with the following purpose: {app_description}

This application is being rendered to a user in their browser. Your job is to generate HTML to represent the current view of the application.

Please generate standard HTML (no external dependencies, inline CSS is fine) to render the home screen of this application to the user.

IMPORTANT: For any interactive elements (buttons, links, form submissions, etc.) that you want to receive events for:
1. Assign them a unique ID attribute
2. Add the attribute data-interactive="true" to mark them as interactive

When the user clicks on an element with data-interactive="true", that interaction will be sent back to you. For input fields and textareas with data-interactive="true", pressing Enter will also trigger the event. This allows you to update the application state and generate a new view.

Elements without data-interactive="true" will NOT trigger events, even if they have IDs. This allows you to have input fields, text areas, and other elements that don't need to trigger view updates.

Example:
<button id="submit-button" data-interactive="true">Submit</button>  <!-- Will trigger events on click -->
<input id="task-input" data-interactive="true" type="text" />  <!-- Will trigger events on click AND Enter key -->
<input id="filter-input" type="text" />  <!-- Will NOT trigger events (user can type freely) -->

Please output ONLY the HTML code, without any markdown formatting or explanation."""


def create_interaction_prompt(element_id: str, form_data: Dict[str, str]) -> str:
    """
    Create a prompt for when the user interacts with an element.
    """
    form_data_str = ""
    if form_data:
        form_data_str = f"\n\nCurrent form field values:\n{json.dumps(form_data, indent=2)}"

    return f"""The user has just interacted with the element with id "{element_id}" (either by clicking it, or by pressing Enter if it's an input field).{form_data_str}

Please process this interaction and decide whether the view needs to be updated.

If the view does NOT need to change (for example, if this was an invalid action, or you're just processing something in the background without a visible change), simply respond with exactly:
NO_CHANGE

If the view DOES need to change, generate an updated HTML view to represent the new state of the application to the user.

Remember to:
1. Assign unique IDs to interactive elements and mark them with data-interactive="true"
2. Input fields and textareas with data-interactive="true" will trigger events on both click and Enter key
3. Elements without data-interactive="true" will not trigger events (useful for input fields that don't need to trigger updates)
4. Output ONLY the HTML code (or NO_CHANGE), without any markdown formatting or explanation
5. Use standard HTML with inline CSS if needed"""


@app.get("/")
async def get():
    """
    Serve the main HTML page.
    """
    with open("index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication with the frontend.
    """
    await websocket.accept()

    # Create a unique session ID for this WebSocket connection
    session_id = str(uuid.uuid4())
    session = SessionState()
    sessions[session_id] = session

    print(f"New session created: {session_id}")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "init":
                # Initialize the application with user's description
                session.application_description = data.get("description", "")
                session.conversation_history = []  # Reset history

                print(f"Session {session_id} - Initializing application: {session.application_description}")

                # Generate initial HTML (runs in thread pool)
                initial_prompt = create_initial_prompt(session.application_description)
                html_response = await get_llm_response(session, initial_prompt)

                # Send HTML back to client
                await websocket.send_json({
                    "type": "html",
                    "content": html_response
                })

            elif message_type == "interaction":
                # Handle user interaction with an element
                element_id = data.get("elementId", "")
                form_data = data.get("formData", {})

                print(f"Session {session_id} - User clicked element: {element_id}")
                if form_data:
                    print(f"Form data: {form_data}")

                # Generate prompt for interaction (runs in thread pool)
                interaction_prompt = create_interaction_prompt(element_id, form_data)
                html_response = await get_llm_response(session, interaction_prompt)

                # Check if the LLM indicated no change is needed
                if html_response.strip() == "NO_CHANGE":
                    print("LLM indicated no view change needed")
                    # Send no-change message back to client
                    await websocket.send_json({
                        "type": "no_change"
                    })
                else:
                    # Send updated HTML back to client
                    await websocket.send_json({
                        "type": "html",
                        "content": html_response
                    })

    except WebSocketDisconnect:
        print(f"Session {session_id} - Client disconnected")
    except Exception as e:
        print(f"Session {session_id} - WebSocket error: {e}")
    finally:
        # Always clean up session data when connection closes
        if session_id in sessions:
            del sessions[session_id]
            print(f"Session {session_id} - Cleaned up session data")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
