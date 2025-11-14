# LLM Application Simulator

An interactive web application that uses Claude AI to simulate any application you can imagine. The LLM generates HTML views on-the-fly based on user interactions.

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

1. When you first open the application, you'll be prompted to describe the type of application you want to simulate (e.g., "A todo list manager", "A calculator", "A simple game").

2. The LLM will generate an initial HTML view for the home screen of that application.

3. You can interact with any element that has an ID assigned to it. When you click on such an element:
   - The click event and any form field values are sent to the backend
   - The LLM processes the interaction and generates an updated HTML view
   - The new view is rendered in your browser

4. This cycle continues indefinitely, allowing you to interact with the simulated application as if it were a real app.

## Features

- Real-time interaction using WebSockets
- Full conversation history maintained with the LLM
- Automatic form data capture on interactions
- Simple, clean UI for the simulation

## Notes

- The application uses Claude Haiku 4.5 for fast response times
- Each interaction maintains context from previous interactions
- The LLM is encouraged to assign IDs to interactive elements
- Errors are logged to the terminal where the server is running
