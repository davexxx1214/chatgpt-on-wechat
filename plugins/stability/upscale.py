import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/upscale/creative",
    headers={
        "authorization": f"Bearer sk-xxx",
        "accept": "image/*"
    },
    files={
        "image": open("./starlink.jpg", "rb")
    },
    data={
        "prompt": "more details",
        "output_format": "webp",
    },
)

print("Generation ID:", response.json().get('id'))