import os
import requests

api_key = os.getenv("STABILITY_API_KEY", "sk-xxx")

if api_key is None:
    raise Exception("Missing Stability API key.")

response = requests.post(
    f"https://api.stability.ai/v1/generation/esrgan-v1-x2plus/image-to-image/upscale",
    headers={
        "Accept": "image/png",
        "Authorization": f"Bearer {api_key}"
    },
    files={
        "image": open("./5.jpg", "rb")
    },
    data={
        "width": 1024,
    }
)

if response.status_code != 200:
    raise Exception("Non-200 response: " + str(response.text))

with open(f"./v1_upscaled_image.png", "wb") as f:
    f.write(response.content)
