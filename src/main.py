import os
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from flask import send_from_directory
from ai import extract_intent_and_entities
from datetime import datetime
from zoneinfo import ZoneInfo
from google_calendar import create_reservation




load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
app = Flask(__name__, template_folder=TEMPLATE_DIR)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_API_KEY = os.getenv("TWILIO_API_KEY")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET")
TWILIO_TWIML_APP_SID = os.getenv("TWILIO_TWIML_APP_SID")

KST = ZoneInfo("Asia/Seoul")

def validate_env():
    missing=[]
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_API_KEY:
        missing.append("TWILIO_API_KEY")
    if not TWILIO_API_SECRET:
        missing.append("TWILIO_API_SECRET")
    if not TWILIO_TWIML_APP_SID:
        missing.append("TWILIO_TWIML_APP_SID")
    if missing:
        return missing
    return None

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message":"AI Receptionist backend is running!",
        "status":"ok"
    }),200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":"healthy",
        "service":"ai-receptionist",
        "method":request.method
    }),200

@app.route("/token", methods=["GET"])
def token():
    missing = validate_env()
    if missing:
        return jsonify({
            "ok":False,
            "error":"Missing environment variables.",
            "missing":missing
        }),500
    
    identity = "tanvir-browser-client"
    access_token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity=identity
    )
    voice_grant = VoiceGrant(
        outgoing_application_sid=TWILIO_TWIML_APP_SID,
        incoming_allow=True
    )
    access_token.add_grant(voice_grant)
    jwt_token = access_token.to_jwt()
    if isinstance(jwt_token, bytes):
        jwt_token = jwt_token.decode("utf-8")
    return jsonify({
        "token":jwt_token,
        "identity":identity
    }),200

@app.route("/voice", methods=["GET","POST"])
def voice():
    """
    Twilio calls this route when someone starts a browser or phone call. We answer the call, greet the caller, and gather speech input.
    """
    response = VoiceResponse()
    gather = Gather(input="speech",
                    action=f"{request.url_root}process-speech",
                    method="POST",
                    speech_timeout="auto",
                    language="en-US")
    gather.say(
        "Hello, thank you for calling NOPS Seoul Station Branch. How can I help you today?",
        voice="alice"
    )
    response.append(gather)
    response.say(
        "I didn't catch that. Please call again. Thank you.",
        voice="alice"
    )
    response.hangup()
    return str(response), 200, {"Content-Type": "text/xml"}

@app.route("/process-speech", methods=["GET", "POST"])
def process_speech():
    """
    Twilio sends recognized speech here after the caller speaks.
    Now we send that transcript to Grok for intent + entity extraction.
    """
    speech_result = request.values.get("SpeechResult", "").strip()

    response = VoiceResponse()

    if not speech_result:
        response.say(
            "Sorry, I did not hear anything. Please call again.",
            voice="alice"
        )
        response.hangup()
        return str(response), 200, {"Content-Type": "text/xml"}

    ai_output = extract_intent_and_entities(speech_result)
    print("Speech Result:", speech_result)
    print("AI output:", ai_output)
    if not ai_output.get("ok"):
        response.say(
            "I heard you, but I had trouble understanding your request in the AI system.",
            voice="alice"
        )
        response.say(
            "Please try again later.",
            voice="alice"
        )
        response.hangup()
        return str(response), 200, {"Content-Type": "text/xml"}

    result = ai_output["result"]

    intent = result.get("intent")
    customer_name = result.get("customer_name")
    party_size = result.get("party_size")
    date = result.get("date")
    time_value = result.get("time")

    if intent == "make_reservation":
        missing_fields = []
        if not customer_name:
            missing_fields.append("name")
        if not party_size:
            missing_fields.append("party size")
        if not date:
            missing_fields.append("date")
        if not time_value:
            missing_fields.append("time")
        if missing_fields:
            response.say(
                f"I can help with that. I still need your {', '.join(missing_fields)} to complete the reservation.",
                voice="alice"
            )
            response.hangup()
            return str(response), 200, {"Content-Type": "text/xml"}
        try:
            # TEMPORARY: for now, Grok must return date like 2026-05-18 and time like 19:00
            start_time = datetime.strptime(
                f"{date} {time_value}",
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=KST)
            booking_result = create_reservation(
                customer_name=customer_name,
                party_size=int(party_size),
                start_time=start_time,
                phone=None,
                notes="Created from AI receptionist voice call"
            )
            if booking_result.get("ok"):
                response.say(
                    f"Your reservation is confirmed for {party_size} people on {date} at {time_value}, under the name {customer_name}.",
                    voice="alice"
                )
            else:
                response.say(
                    "Sorry, that time slot is not available. Please choose another time.",
                    voice="alice"
                )
        except Exception as exc:
            print("Booking error:", exc)
            response.say(
                "I understood your reservation request, but I had trouble creating the booking in the calendar.",
                voice="alice"
            )
        
    elif intent == "ask_hours":
        response.say(
            "You are asking about business hours. I will support exact hour answers in the next step.",
            voice="alice"
        )

    elif intent == "ask_menu":
        response.say(
            "You are asking about the menu. Menu question handling will be connected next.",
            voice="alice"
        )

    elif intent == "ask_parking":
        response.say(
            "You are asking about parking. Parking answer logic will be connected next.",
            voice="alice"
        )

    elif intent == "ask_location":
        response.say(
            "You are asking about location. Location answer logic will be connected next.",
            voice="alice"
        )

    else:
        response.say(
            "I understood your speech, but I am not fully sure about your request yet.",
            voice="alice"
        )
        response.say(
            f"You said: {speech_result}",
            voice="alice"
        )

    response.hangup()
    return str(response), 200, {"Content-Type": "text/xml"}

@app.route("/browser", methods=["GET"])
def browser():
    return render_template("browser.html")

@app.route("/twilio.min.js")
def serve_twilio_sdk():
    return send_from_directory(TEMPLATE_DIR, "twilio.min.js")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)