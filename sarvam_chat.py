import os
from pathlib import Path

from dotenv import load_dotenv
from sarvamai import SarvamAI

load_dotenv(Path(__file__).with_name(".env"))

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise SystemExit("Set SARVAM_API_KEY in the environment or .env file.")

client = SarvamAI(api_subscription_key=api_key)
response = client.chat.completions_v2(
    model="glm5.3",
    messages=[{"role": "user", "content": "Reply with a short greeting."}],
    max_tokens=128,
)

print(response.choices[0].message.content)
