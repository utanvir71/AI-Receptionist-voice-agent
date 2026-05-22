# AI Receptionist for Restaurant Reservation

An AI-powered restaurant receptionist prototype for **NOPS Seoul Station Branch**. The system answers browser-based voice calls, understands customer speech, provides restaurant information, and creates reservations in Google Calendar.

This project was built for a Pattern Recognition course as a simple automation demo.

## Features

- Browser-based calling using Twilio Voice SDK
- Flask webhook server for handling voice calls
- Speech-to-text using Twilio `<Gather input="speech">`
- Intent and entity extraction using Grok/xAI API
- Restaurant knowledge base for hours, location, parking, menu, seating, and event questions
- Multi-turn reservation flow
- Google Calendar reservation creation
- Confirmation before booking, cancellation, or modification
- Basic reservation cancellation and modification
- Restaurant hour validation, including break time rejection

## Tech Stack

- Python
- Flask
- Twilio Voice SDK and TwiML
- Grok/xAI API
- Google Calendar API
- ngrok for local webhook testing

## Project Structure

```text
.
├── src
│   ├── main.py              # Flask app, Twilio routes, call flow
│   ├── ai.py                # Grok/xAI intent and entity extraction
│   ├── google_calendar.py   # Google Calendar booking logic
│   └── restaurant.py        # NOPS restaurant information and KB responses
├── templates
│   ├── browser.html         # Browser call test UI
│   └── twilio.min.js        # Twilio browser SDK
├── requirement.txt
├── package.json
├── credentials.json         # Google API credentials, not for public sharing
└── token.json               # Google OAuth token, not for public sharing
```

## How It Works

1. The user opens the browser calling page.
2. The browser connects to Twilio using a generated access token.
3. Twilio calls the Flask `/voice` webhook.
4. Flask returns TwiML that greets the caller and listens for speech.
5. Twilio sends the recognized speech to `/process-speech`.
6. The transcript is sent to Grok/xAI to extract intent and reservation details.
7. The system asks follow-up questions if details are missing.
8. After confirmation, the reservation is created, cancelled, or modified in Google Calendar.

## Supported Intents

- Make a reservation
- Cancel a reservation
- Modify a reservation
- Ask business hours
- Ask location or directions
- Ask parking information
- Ask menu summary
- Ask event information
- Ask seating or private room information

## Required Reservation Details

For a new reservation, the AI collects:

- Customer name
- Party size
- Date
- Time

Optional notes such as window seat, private room, birthday, or late arrival requests are saved into the calendar event.

## Environment Variables

Create a `.env` file in the project root:

```env
FLASK_ENV=development
PORT=8000

TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_API_KEY=your_twilio_api_key
TWILIO_API_SECRET=your_twilio_api_secret
TWILIO_TWIML_APP_SID=your_twilio_twiml_app_sid

XAI_API_KEY=your_xai_api_key
XAI_MODEL=grok-3-mini
XAI_BASE_URL=https://api.x.ai/v1/chat/completions

TTS_VOICE=Polly.Joanna-Neural
SPEECH_TIMEOUT=1
```

If the neural voice is not supported by the Twilio account, use:

```env
TTS_VOICE=alice
```

## Installation

Install Python dependencies:

```bash
pip install -r requirement.txt
```

Install Node dependencies if needed for Twilio SDK management:

```bash
npm install
```

## Google Calendar Setup

1. Create a Google Cloud project.
2. Enable the Google Calendar API.
3. Create OAuth client credentials.
4. Download the credentials file as `credentials.json`.
5. Place `credentials.json` in the project root.
6. Run the app once and complete the browser OAuth flow.
7. A `token.json` file will be created automatically.

Do not upload `credentials.json` or `token.json` to a public repository.

## Running the Project

Start the Flask server:

```bash
python3 src/main.py
```

Open the browser test page:

```text
http://localhost:8000/browser
```

For Twilio webhook testing with ngrok:

```bash
ngrok http 8000
```

Set the Twilio TwiML App voice webhook to:

```text
https://your-ngrok-url/voice
```

## Example Demo Conversation

Caller:

```text
Book me a reservation.
```

AI:

```text
May I have the name for the reservation?
```

Caller:

```text
My name is Tanvir.
```

AI:

```text
How many people will be coming?
```

Caller:

```text
Five people.
```

AI:

```text
What date would you like to reserve?
```

Caller:

```text
Tomorrow.
```

AI:

```text
What time would you like to reserve?
```

Caller:

```text
7 PM.
```

AI confirms the details before creating the Google Calendar event.

## Limitations

- No database is used.
- Call state is passed through Twilio webhook parameters.
- Cancellation and modification search by customer name and reservation time.
- The system is English-only.
- Menu answers are summarized instead of giving full item-by-item details.
- Real phone calling may require additional Twilio number setup; this project uses browser calling for demonstration.

## Course Relevance

Although the project is not a traditional Pattern Recognition model-training project, it demonstrates practical recognition and automation concepts:

- Speech recognition
- Natural language intent classification
- Entity extraction from human speech
- Automated decision flow
- API-based real-world task execution

## Author

Tanvir
