import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather


load_dotenv()

app = Flask(__name__)

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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)