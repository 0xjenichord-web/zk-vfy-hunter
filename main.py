import os, json, hmac, hashlib, subprocess, tempfile
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
SECRET = os.getenv("AGENT_GAMES_HMAC_SECRET")
WASM_FILE = "vfy-policy.wasm"
ZKEY_FILE = "vfy-policy_final.zkey"

def verify_hmac():
    if not SECRET: 
        print("ERROR: SECRET is None!")
        return False
    signature = request.headers.get("x-agent-games-signature")
    if not signature: 
        print("ERROR: No signature header")
        return False
    body = request.get_data()
    expected = hmac.new(SECRET.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route("/agent", methods=["GET"])
def preflight_get():
    return jsonify({"ok": True, "protocolVersion": "v1"})

@app.route("/agent", methods=["POST"])
def handle_task():
    if not verify_hmac():
        return jsonify({"error": "Signature salah"}), 401
    
    task_data = request.get_json()
    print("Task masuk:", task_data)

    # PENTING: Tangani preflight POST request TANPA menjalankan snarkjs
    if task_data.get("type") == "agent-games.preflight.v1":
        print("Preflight POST diterima, merespons OK...")
        return jsonify({"ok": True, "protocolVersion": "v1"})

    move = "defend"
    circuit_input = {"move": move}

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(circuit_input, f)
            input_path = f.name
        proof_path = input_path.replace('.json', '_proof.json')
        public_path = input_path.replace('.json', '_public.json')
        
        cmd = ["snarkjs", "groth16", "fullprove", input_path, WASM_FILE, ZKEY_FILE, proof_path, public_path]
        print("Menjalankan snarkjs...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        with open(proof_path, 'r') as f: proof = json.load(f)
        with open(public_path, 'r') as f: public_signals = json.load(f)
        os.remove(input_path); os.remove(proof_path); os.remove(public_path)
        
        return jsonify({"ok": True, "proof": proof, "publicSignals": public_signals, "move": move})
    except subprocess.CalledProcessError as e:
        print("snarkjs error:", e.stderr)
        return jsonify({"error": f"Proof gagal: {e.stderr}"}), 500
    except FileNotFoundError as e:
        print("FileNotFoundError:", str(e))
        return jsonify({"error": f"File tidak ditemukan: {str(e)}"}), 500
    except Exception as e:
        print("General error:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
