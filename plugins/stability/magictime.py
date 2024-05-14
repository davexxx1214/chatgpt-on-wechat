import replicate
import os

# 设置环境变量REPLICATE_API_TOKEN
os.environ['REPLICATE_API_TOKEN'] = 'r8_xxx'

# 使用api_token发送请求...

input =  {
"prompt":"Bean sprouts grow and mature from seeds.",
"n_prompt":  "worst quality, low quality, nsfw, logo",
"width":  512,
"height":  512,
"seed":  "-1",
"dreambooth":  "RealisticVisionV60B1_v51VAE.safetensors"
}

output = replicate.run(
    "camenduru/magictime:91e4bb80b45832b5bafdbc10d94fd1d364d0d6ad80f5b1498fcb25d217cb3a9c",
    input=input
)
print(output)
#=> "https://replicate.delivery/pbxt/OtpFsf7A39zFYSxYkuAIieie...