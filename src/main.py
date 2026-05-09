import os
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant


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
                    action="/process-speech",
                    method="POST",
                    speech_timeout="auto",
                    language="en-US")
    gather.say("hello, Thank you for calling NOPS Seoul Station Branch. How can i help you today?" ,
        voice = "alice"
    )
    response.append(gather)
    response.say(
        "I didn't catch that. Please call again. Thank you.",
        voice="alice"
    )
    response.hangup()
    return str(response)

@app.route("/process-speech", methods=["POST"])
def process_speech():
    """
    Twilio sends recognized speech here after the caller speaks.
    For nowk, we just repat back what we heard.
    In phase 3, this goes to Grok for intent/entity extraction.
    """
    speech_result = request.form.get("SpeechResult", "").strip()
    response = VoiceResponse()
    if speech_result:
        response.say(f"You said:{speech_result}." 
                     "This is a test of the AI receptionist system. in the future, this is where the AI response will be generated based on your request.",
                     voice="alice")
    else:
        response.say(
            "Sorry, I did not hear anything. Please call again.",
            voice="alice"
        )
    response.hangup()
    return str(response), 200, {"content-type":"text/xml"}


@app.route("/browser", methods=["GET"])
def browser():
    return render_template("browser.html")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)