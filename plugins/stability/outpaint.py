import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/edit/outpaint",
    headers={
        "authorization": f"Bearer sk-xxx",
        "accept": "image/*"
    },
    files={
        "image": open("./boy.png", "rb")
    },
    data={
        "left": 512,
        "down": 512,
        "right":512,
        "up":512,
        "prompt":"",
        "output_format": "jpeg"
    },
)

if response.status_code == 200:
    with open("./result.jpg", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))