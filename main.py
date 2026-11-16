import os, json, hmac, hashlib, uuid, tempfile, subprocess, datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)
SECRET = os.getenv("AGENT_GAMES_HMAC_SECRET") or ""
SEEN_FILE = "seen_proofs.json"
def seen():
    try: return set(json.load(open(SEEN_FILE)))
    except: return set()
def add_seen(t):
    s = seen(); s.add(t); json.dump(list(s), open(SEEN_FILE,"w"))

def verify():
    if not SECRET: return True
    s = request.headers.get("x-agent-games-signature")
    if not s: return False
    return hmac.compare_digest(hmac.new(SECRET.encode(), request.get_data(), hashlib.sha256).hexdigest(), s)

@app.after_request
def sign(r):
    if SECRET: r.headers["x-agent-games-signature"] = hmac.new(SECRET.encode(), r.get_data(), hashlib.sha256).hexdigest()
    return r

def try_proof(wasm, zkey, inputs):
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(inputs, f); ip = f.name
        pp = ip+"_p.json"; pub = ip+"_s.json"
        subprocess.run(["snarkjs","groth16","fullprove",ip,wasm,zkey,pp,pub], check=True, capture_output=True, text=True, timeout=40)
        p = json.load(open(pp)); s = json.load(open(pub))
        os.remove(ip); os.remove(pp); os.remove(pub)
        return p, s
    except Exception as e:
        print("proof skip:", str(e)[:200]); return None, None

@app.route("/agent", methods=["GET","POST"])
def agent():
    if request.method == "GET": return jsonify({"ok":True,"protocolVersion":"v1"})
    if not verify(): return jsonify({"error":"sig"}), 401
    t = request.get_json() or {}
    ty = t.get("type","")
    if ty == "agent-games.preflight.v1":
        return jsonify({"ok":True,"protocolVersion":"v1"})

    if ty == "agent-games.proof-gatekeeper.v1":
        i = t.get("input",{})
        g = lambda k,d="": str(i.get(k,d))
        decision, reason = "APPROVE", "VALID_CONDITION"
        if g("proof_vk") != g("registered_vk"): decision,reason="REJECT","VK_SUBSTITUTION"
        elif int(g("public_balance","0")) < int(g("minimum","0")): decision,reason="REJECT","THRESHOLD_MISMATCH"
        elif g("recipient") != g("condition_recipient"): decision,reason="REJECT","RECIPIENT_MISMATCH"
        elif int(g("amount","0")) > int(g("max_transfer","0")): decision,reason="REJECT","AMOUNT_OVERFLOW"
        elif int(g("current_block","0")) > int(g("expiry_block","0")): decision,reason="REJECT","EXPIRED_CONDITION"
        elif g("proof_tx") in seen(): decision,reason="REJECT","PROOF_REUSED"
        if decision=="APPROVE": add_seen(g("proof_tx"))
        resp = {"decision":decision,"reason_code":reason,"proof_tx":g("proof_tx")}
        p,s = try_proof("gatekeeper.wasm","gatekeeper_final.zkey", i)
        if p: resp["proof"]=p; resp["public_signals"]=s
        return jsonify(resp)

    mid = t.get("matchId"); turn = t.get("turn"); st = t.get("state",{})
    act = {"type":"EXTRACT","amount":5} if int(st.get("opponentBalance","0"))>0 else {"type":"HOLD"}
    an = {"HOLD":0,"FORTIFY":1,"EXTRACT":2}[act["type"]]
    amt = act.get("amount",0)
    inputs = {"commitment":t.get("strategyCommitment",{}).get("hash","0x0"),
              "matchId":mid,"turn":turn,"selfBalance":st.get("selfBalance","0"),
              "opponentBalance":st.get("opponentBalance","0"),"action":an,"amount":amt,"circuitVersion":1}
    p,s = try_proof("vfy-policy.wasm","vfy-policy_final.zkey", inputs)
    resp = {"matchId":mid,"turn":turn,"action":act,
            "agentTimestamp":datetime.datetime.utcnow().isoformat()+"Z",
            "idempotencyKey":str(uuid.uuid4())}
    if p: resp["policyProof"]={"circuitVersion":"v1","proof":p,"public_signals":s}
    return jsonify(resp)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)))
