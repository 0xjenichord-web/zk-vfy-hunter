import os, json, hmac, hashlib, subprocess, tempfile
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
SECRET = os.getenv("AGENT_GAMES_HMAC_SECRET") or ""
WASM_FILE = "vfy-policy.wasm"
ZKEY_FILE = "vfy-policy_final.zkey"

def verify_hmac():
    if not SECRET: return True
    sig = request.headers.get("x-agent-games-signature")
    if not sig: return False
    exp = hmac.new(SECRET.encode(), request.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(exp, sig)

# INI KUNCINYA: tandatangani SETIAP respons
@app.after_request
def sign_response(resp):
    if SECRET:
        sig = hmac.new(SECRET.encode(), resp.get_data(), hashlib.sha256).hexdigest()
        resp.headers["x-agent-games-signature"] = sig
    return resp

@app.route("/agent", methods=["GET"])
def preflight_get():
    return jsonify({"ok": True, "protocolVersion": "v1"})

@app.route("/agent", methods=["POST"])
def handle_task():
    if not verify_hmac():
        return jsonify({"error": "Signature salah"}), 401
    task = request.get_json() or {}
    print("Task masuk:", task.get("type"))
    if task.get("type") == "agent-games.preflight.v1":
        return jsonify({"ok": True, "protocolVersion": "v1"})
    move = "defend"
    ci = {"move": move}
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(ci, f); ip = f.name
        pp = ip.replace(".json","_proof.json"); pub = ip.replace(".json","_public.json")
        subprocess.run(["snarkjs","groth16","fullprove",ip,WASM_FILE,ZKEY_FILE,pp,pub], check=True, capture_output=True, text=True)
        proof = json.load(open(pp)); signals = json.load(open(pub))
        os.remove(ip); os.remove(pp); os.remove(pub)
        data = {"ok": True, "proof": proof, "publicSignals": signals, "move": move}
        if len(json.dumps(data)) > 15000: data["publicSignals"] = signals[:10]
        return jsonify(data)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Proof gagal: " + e.stderr[-800:]}), 500
    except Exception as e:
        return jsonify({"error": str(e)[-800:]}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
