import requests

generation_id = "a992888d3994757c907e42dec044bd3100112bc85aa64cd3c8b23ab7c2881a1f"

response = requests.request(
    "GET",
    f"https://api.stability.ai/v2beta/stable-image/upscale/creative/result/{generation_id}",
    headers={
        'Accept': "image/*",  # Use 'application/json' to receive base64 encoded JSON
        'authorization': f"Bearer sk-xxx"
    },
)


print(response.status_code)

if response.status_code == 202:
    print("Generation in-progress, try again in 10 seconds.")
elif response.status_code == 200:
    print("Generation complete!")
    with open("upscaled.png", 'wb') as file:
        file.write(response.content)
else:
    raise Exception(str(response.json()))