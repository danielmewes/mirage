import os
import json
import re
from typing import List, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Store conversation history (single user session)
conversation_history: List[Dict[str, str]] = []
application_description: str = ""


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


def get_llm_response(user_message: str) -> str:
    """
    Send a message to the LLM and get the HTML response.
    """
    # Add user message to history
    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    try:
        # Call Anthropic API
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=conversation_history
        )

        # Extract the assistant's response
        assistant_message = response.content[0].text

        # Add assistant response to history
        conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        # Strip markdown code blocks before returning
        cleaned_html = strip_markdown_code_blocks(assistant_message)
        return cleaned_html

    except Exception as e:
        print(f"Error calling Anthropic API: {e}")
        raise


def create_initial_prompt(app_description: str) -> str:
    """
    Create the initial prompt for the LLM to generate the home screen.
    """
    return f"""You're an application with the following purpose: {app_description}

This application is being rendered to a user in their browser. Your job is to generate HTML to represent the current view of the application.

Please generate standard HTML (no external dependencies, inline CSS is fine) to render the home screen of this application to the user.

IMPORTANT: For any interactive elements (buttons, links, form submissions, etc.) that you want the user to be able to interact with, assign them a unique ID attribute. When the user clicks on an element with an ID, that interaction will be sent back to you so you can update the application state and generate a new view.

Please output ONLY the HTML code, without any markdown formatting or explanation."""


def create_interaction_prompt(element_id: str, form_data: Dict[str, str]) -> str:
    """
    Create a prompt for when the user interacts with an element.
    """
    form_data_str = ""
    if form_data:
        form_data_str = f"\n\nCurrent form field values:\n{json.dumps(form_data, indent=2)}"

    return f"""The user has just clicked on the element with id "{element_id}".{form_data_str}

Please process this interaction and decide whether the view needs to be updated.

If the view does NOT need to change (for example, if this was an invalid action, or you're just processing something in the background without a visible change), simply respond with exactly:
NO_CHANGE

If the view DOES need to change, generate an updated HTML view to represent the new state of the application to the user.

Remember to:
1. Assign unique IDs to any interactive elements
2. Output ONLY the HTML code (or NO_CHANGE), without any markdown formatting or explanation
3. Use standard HTML with inline CSS if needed"""


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
    global conversation_history, application_description

    await websocket.accept()

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "init":
                # Initialize the application with user's description
                application_description = data.get("description", "")
                conversation_history = []  # Reset history

                print(f"Initializing application: {application_description}")

                # Generate initial HTML
                initial_prompt = create_initial_prompt(application_description)
                html_response = get_llm_response(initial_prompt)

                # Send HTML back to client
                await websocket.send_json({
                    "type": "html",
                    "content": html_response
                })

            elif message_type == "interaction":
                # Handle user interaction with an element
                element_id = data.get("elementId", "")
                form_data = data.get("formData", {})

                print(f"User clicked element: {element_id}")
                if form_data:
                    print(f"Form data: {form_data}")

                # Generate prompt for interaction
                interaction_prompt = create_interaction_prompt(element_id, form_data)
                html_response = get_llm_response(interaction_prompt)

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
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
