import requests

response = requests.post(
    f"https://api.stability.ai/v2beta/stable-image/generate/sd3",
    headers={
        "authorization": f"Bearer sk-xxx",
        "accept": "image/*"
    },
    files={
        "none": ''
    },
    data={
        "prompt": "a dragon footprint with cyber style",
        "model": "sd3",
        "output_format": "png",
    },
)

if response.status_code == 200:
    with open("./result.png", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))