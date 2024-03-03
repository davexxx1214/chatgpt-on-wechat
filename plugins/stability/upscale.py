import requests

response = requests.post(
    f"https://api.stability.ai/v2alpha/generation/stable-image/upscale",
    headers={
        "authorization": f"Bearer sk-cLs0cQbfHs4xPttTgTjULZu2X1a1N15QxIfQvDlsHGVBpxN2"
    },
    files={
        "image": open("./5.jpg", "rb")
    },
    data={
        "prompt": "a girl",
        "output_format": "jpeg",
    },
)
print("result:", response.json())
print("Generation ID:", response.json().get('id'))