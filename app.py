from flask import Flask, send_from_directory, request, jsonify
import sqlite3
import psycopg2
import stripe
import os

app = Flask(__name__)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sold_cubes (
            cube_id INTEGER PRIMARY KEY,
            sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()
@app.route("/api/sold")
def get_sold():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT cube_id, sold_at FROM sold_cubes")
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "sold": [
            {"cube_id": row[0], "sold_at": str(row[1])}
            for row in rows
        ]
    }
@app.route("/api/sold", methods=["POST"])
def add_sold():
    data = request.get_json()
    cube_id = int(data["cube_id"])

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO sold_cubes (cube_id) VALUES (%s)",
            (cube_id,)
        )
        conn.commit()

    except psycopg2.IntegrityError:
        conn.rollback()
        cur.close()
        conn.close()
        return {"ok": False, "error": "already_sold"}, 409

    cur.close()
    conn.close()

    return {"ok": True, "cube_id": cube_id}

@app.route("/api/create-checkout-session", methods=["POST"])
def create_checkout_session():
    data = request.get_json()
    cube_id = int(data["cube_id"])
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {
                    "name": f"Cubetto #{cube_id}",
                },
                "unit_amount": 300,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url="https://million-cube.onrender.com/?payment=success",
        cancel_url="https://million-cube.onrender.com/?payment=cancel",
        metadata={"cube_id": str(cube_id)},
    )

    return {"url": session.url}
@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    endpoint_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            endpoint_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return {"error": "invalid webhook"}, 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        cube_id = int(session["metadata"]["cube_id"])

        conn = get_conn()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO sold_cubes (cube_id) VALUES (%s) ON CONFLICT (cube_id) DO NOTHING",
            (cube_id,)
        )

        conn.commit()
        cur.close()
        conn.close()

    return {"ok": True}, 200
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

if __name__ == "__main__":
    app.run(debug=True, port=8000)
