from flask import Flask, jsonify, render_template
from pymongo import MongoClient

app = Flask(__name__)
db = MongoClient("mongodb://localhost:27017")["pm3"]


@app.route("/")
def startseite():
    return render_template("index.html")


@app.route("/api/cafes")
def cafes():
    daten = db.amenities.find({}, {"_id": 0})
    return jsonify(list(daten))


@app.route("/api/gemeinden")
def gemeinden():
    daten = db.municipalities.find({})
    return jsonify(list(daten))


app.run(debug=True, port=5000)
