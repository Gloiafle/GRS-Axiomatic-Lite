import json
import hashlib

def register_to_shard(bio_data):
    """Binds a citizen's PZR signature to the AEA Ledger."""
    shard_db = "lite_ledger.json"
    citizen_hash = hashlib.sha256(bio_data.encode()).hexdigest()
    
    entry = {
        "id": citizen_hash,
        "status": "SOVEREIGN_FREE",
        "energy_access": "UNLIMITED"
    }
    
    # Atomic Write
    try:
        with open(shard_db, 'a') as f:
            f.write(json.dumps(entry) + "\n")
        return f"SUCCESS: Citizen {citizen_hash[:8]} is now Axiomatic."
    except Exception as e:
        return f"ERROR: Registration failed: {e}"

print(register_to_shard("PZR-DELTA-SIG-001"))
