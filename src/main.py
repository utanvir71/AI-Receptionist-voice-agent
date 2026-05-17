import os
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from flask import send_from_directory
from ai import extract_intent_and_entities



load_dotenv()

app = Flask(__name__, template_folder="../templates")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_API_KEY = os.getenv("TWILIO_API_KEY")
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET")
TWILIO_TWIML_APP_SID = os.getenv("TWILIO_TWIML_APP_SID")

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
        "message":"AI Receptionst backend is running!",
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
            "error":"Missing environment vairables.",
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
    Twillio call this route when someone calls your Twilio number. We answer the call, greet the caller, and gather speech intput.
    """
    response = VoiceResponse()
    gather = Gather(input="speech",
                    action=f"{request.url_root}process-speech",
                    method="POST",
                    speech_timeout="auto",
                    language="en-US")
    gather.say("hello, Thank you for calling Nops Seoul Station Branch. How can i help you today?" ,
        voice = "alice"
    )
    response.append(gather)
    response.say(
        "I didn't catch that. Please call again. Thank you.",
        voice="alice"
    )
    response.hangup()
    return str(response), 200, {"content-Type":"text/xml"}

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
    print("Speach Result:", speech_result)
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
        summary_parts = []

        if party_size:
            summary_parts.append(f"for {party_size} people")
        if date:
            summary_parts.append(f"on {date}")
        if time_value:
            summary_parts.append(f"at {time_value}")
        if customer_name:
            summary_parts.append(f"under the name {customer_name}")

        summary_text = ", ".join(summary_parts) if summary_parts else "but some details are still missing"

        response.say(
            f"Got it. You want to make a reservation {summary_text}.",
            voice="alice"
        )
        response.say(
            "This is the AI extraction test. In the next phase, I will save this booking to Google Calendar.",
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
    return send_from_directory("../templates", "twilio.min.js")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)