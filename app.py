from flask import Flask, request

app = Flask(__name__)


@app.route("/")
def home():
    return "LINE Bot OK"


@app.route("/callback", methods=["GET", "POST"])
def callback():

    if request.method == "GET":
        return "Callback OK", 200

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
