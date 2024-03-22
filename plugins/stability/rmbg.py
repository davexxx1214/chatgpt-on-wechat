import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/edit/remove-background",
    headers={
        "authorization": f"Bearer sk-xxx",
        "accept": "image/*"
    },
    files={
        "image": open("./1.jpg", "rb")
    },
    data={
        "output_format": "webp"
    },
)

if response.status_code == 200:
    with open("./husky.webp", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))