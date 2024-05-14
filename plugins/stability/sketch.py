import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/control/sketch",
    headers={
        "authorization": f"Bearer sk-YmPiZN5dREYUyWIvOoHfDtOgiQ1rl0hu3IRV9IEfyxspxzCx",
        "accept": "image/*"
    },
    files={
        "image": open("./sketch.png", "rb")
    },
    data={
        "prompt": "beatiful girl is running",
        "control_strength": 1,
        "output_format": "png"
    },
)

if response.status_code == 200:
    with open("./result.png", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))