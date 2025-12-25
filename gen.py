import secrets

# Generate a secure random key
secret_key = secrets.token_hex(32)

print("=" * 60)
print("🔑 Flask SECRET_KEY Generator")
print("=" * 60)
print("\nYour secure SECRET_KEY:")
print("-" * 60)
print(secret_key)
print("-" * 60)
print("\n📝 Instructions:")
print("1. Copy the key above")
print("2. Open your .env file")
print("3. Add this line:")
print(f"\n   SECRET_KEY={secret_key}")
print("\n✅ Done! Your Flask app will now use this key for sessions.")
print("=" * 60)