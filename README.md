# Mirage

Use an LLM to hallucinate any web application you can imagine. Just type in a description of the app and interact with it right away!

The LLM generates HTML views on-the-fly based on your interactions.

Currently uses Claude Haiku and requires an Anthropic API key to work.

See this [blog post for examples](https://amongai.com/2025/12/10/hallucinate-any-app-one-screen-at-a-time/).

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your Anthropic API key:
```bash
cp .env.example .env
# Edit .env and add your API key
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to:
```
http://localhost:8000
```

## How It Works

1. When you first open the application, you'll be prompted to describe the type of application you want to use (e.g., "A todo list manager", "A calculator", "A simple game").

2. The LLM will generate an initial HTML view for the home screen of that application.

3. You can interact with any element that has an ID assigned to it. When you click on such an element:
   - The click event and any form field values are sent to the backend
   - The LLM processes the interaction and generates an updated HTML view
   - The new view is rendered in your browser

4. This cycle continues indefinitely, allowing you to interact with the simulated application as if it were a real app.

## Notes & Limitations

- This is very much just a proof of concept. Not meant for serious use.
- Each interaction maintains context from previous interactions in the same session. Though you might eventually run out of available context window.
- There isn't any persistent state across sessions
- Not all UI interactions are supported. Mainly, button clicks and text input submissions will work, but things like drawing or dragging things will not.
- Errors are logged to the terminal where the server is running
