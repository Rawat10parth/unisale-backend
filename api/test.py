from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({
        "message": "API is working",
        "status": "success"
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "UniSale API is running",
        "version": "1.0.0"
    })
