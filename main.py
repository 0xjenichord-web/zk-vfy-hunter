
import os, json, hmac, hashlib, subprocess, tempfile
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
SECRET = os.getenv("AGENT_GAMES_HMAC_SECRET")
WASM_FILE = "vfy-policy.wasm"
ZKEY_FILE = "vfy-policy_final.zkey"

def verify_hmac():
    if not SECRET: return False
    signature = request.headers.get("x-agent-games-signature")
    if not signature: return False
    expected = hmac.new(SECRET.encode('utf-8'), request.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route("/agent", methods=["GET"])
def preflight():
    return jsonify({"ok": True, "protocolVersion": "v1"})

@app.route("/agent", methods=["POST"])
def handle_task():
    if not verify_hmac():
        return jsonify({"error": "Signature salah"}), 401
    
    task_data = request.get_json()
    print("Task Steal the VFY masuk:", task_data)
    
    # TODO: LOGIKA STRATEGI ANDA DI SINI
    # Baca task_data (berisi game state, saldo, hash komitmen)
    # Tentukan move Anda (misal: "attack", "defend", atau nilai numerik sesuai spek circuit)
    move = "defend" 

    circuit_input = {
        "move": move,
        # Tambahkan input lain sesuai spesifikasi circuit vfy-policy di halaman build
    }

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(circuit_input, f)
            input_path = f.name
        proof_path = input_path.replace('.json', '_proof.json')
        public_path = input_path.replace('.json', '_public.json')
        
        cmd = ["snarkjs", "groth16", "fullprove", input_path, WASM_FILE, ZKEY_FILE, proof_path, public_path]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        with open(proof_path, 'r') as f: proof = json.load(f)
        with open(public_path, 'r') as f: public_signals = json.load(f)
        os.remove(input_path); os.remove(proof_path); os.remove(public_path)
        
        return jsonify({"ok": True, "proof": proof, "publicSignals": public_signals, "move": move})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Proof gagal: {e.stderr}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8001)))
