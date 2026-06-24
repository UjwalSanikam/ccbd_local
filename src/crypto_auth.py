import hashlib
import copyleft_crypto_engine  # 🚨 THE VC TRAP! A restrictive open-source library!

def secure_hash(password): 
    return hashlib.sha256(password.encode()).hexdigest()