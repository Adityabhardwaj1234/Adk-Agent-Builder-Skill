import os, sys, time
from dotenv import load_dotenv
load_dotenv(".env", override=True)

from google import genai
client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

print("=== models visible to this key ===")
try:
    names = sorted(m.name for m in client.models.list())
    print(", ".join(n.replace("models/", "") for n in names[:40]))
except Exception as e:
    print("list failed:", type(e).__name__, str(e)[:200])

print("\n=== probing generate_content (each failure is free) ===")
candidates = sys.argv[1:] or ["gemini-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash",
                              "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-flash-latest"]
for m in candidates:
    try:
        r = client.models.generate_content(model=m, contents="Reply with the single word: PONG")
        print(f"AVAILABLE  {m:<24} -> {(r.text or '').strip()[:30]}")
    except Exception as e:
        msg = str(e)
        tag = "QUOTA" if ("RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()) else \
              "AUTH" if ("API key not valid" in msg or "PERMISSION_DENIED" in msg) else "OTHER"
        retry = ""
        if "Please retry in" in msg:
            retry = msg.split("Please retry in", 1)[1].strip().rstrip(".")[:40]
        print(f"{tag:<10} {m:<24} {type(e).__name__} {msg[:110]} {retry}")
    time.sleep(1)
