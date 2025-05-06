from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": ["https://unisale-frontend.vercel.app", "https://unisale-1556d.web.app", "http://localhost:5173"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Welcome to UniSale API!"})

@app.route("/api/test", methods=["GET"])
def test():
    return jsonify({"status": "success", "message": "API is working!"})
