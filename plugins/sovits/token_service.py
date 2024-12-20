import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
from urllib.parse import quote

import requests

# 服务相关参数
Service = "sami"  # 设置为 'sami' 服务
Version = "2021-07-27"  # API版本，与 Node.js 代码保持一致
Region = "cn-north-1"  # 区域
Host = "open.volcengineapi.com"  # 使用 'sami' 服务的主机
ContentType = "application/json"  # 内容类型与 Node.js 代码一致

# 从配置文件中读取 AK 和 SK
config_path = Path(__file__).parent / 'config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

AK = config.get('huoshan_access_key')  # Access Key ID
SK = config.get('huoshan_secret_key')  # Secret Access Key
APPKEY = config.get('huoshan_app_key')  # App Key

# Token 缓存文件路径
TOKEN_CACHE_PATH = Path(__file__).parent / 'token_cache.json'

def norm_query(params):
    query = ""
    for key in sorted(params.keys()):
        if isinstance(params[key], list):
            for k in params[key]:
                query += f"{quote(str(key), safe='-_.~')}={quote(str(k), safe='-_.~')}&"
        else:
            query += f"{quote(str(key), safe='-_.~')}={quote(str(params[key]), safe='-_.~')}&"
    return query[:-1].replace("+", "%20")

def hmac_sha256(key: bytes, content: str):
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()

def hash_sha256(content: str):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def get_signature_key(key, date_stamp, region, service):
    k_date = hmac_sha256(key, date_stamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    return k_signing

def load_cached_token():
    if TOKEN_CACHE_PATH.exists():
        with open(TOKEN_CACHE_PATH, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            expires_at = cache.get('expires_at', 0)
            current_time = int(datetime.datetime.utcnow().timestamp())
            if current_time < expires_at:
                return cache.get('token')
    return None

def save_token(token, expires_at):
    cache = {
        'token': token,
        'expires_at': expires_at
    }
    with open(TOKEN_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f)

def get_token():
    # 首先尝试从缓存中加载 Token
    cached_token = load_cached_token()
    if cached_token:
        print("使用缓存中的 Token。")
        return cached_token

    method = 'POST'
    service = Service
    host = Host
    region = Region
    endpoint = f'https://{host}/'
    path = '/'
    action = 'GetToken'
    version = Version
    token_version = "volc-auth-v1"
    expiration = 86400  # 设置为1天（86400秒）

    # 请求参数
    query_params = {
        "Action": action,
        "Version": version
    }

    # 请求体
    body_params = {
        "token_version": token_version,
        "appkey": APPKEY,
        "expiration": expiration
    }
    body = json.dumps(body_params)

    # 创建时间戳
    t = datetime.datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')

    # 生成规范请求字符串
    canonical_uri = path
    canonical_querystring = norm_query(query_params)
    canonical_headers = f'content-type:{ContentType}\nhost:{host}\nx-date:{amz_date}\n'
    signed_headers = 'content-type;host;x-date'
    payload_hash = hash_sha256(body)
    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

    # 打印调试信息
    print("Canonical Request:")
    print(canonical_request)
    print("Hash of Canonical Request:")
    print(hash_sha256(canonical_request))

    # 创建字符串待签名
    algorithm = 'HMAC-SHA256'
    credential_scope = f"{date_stamp}/{region}/{service}/request"
    string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hash_sha256(canonical_request)}"

    # 打印调试信息
    print("String to Sign:")
    print(string_to_sign)

    # 计算签名
    signing_key = get_signature_key(SK.encode('utf-8'), date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    # 打印签名
    print("Signature:")
    print(signature)

    # 构建 Authorization 头
    authorization_header = (
        f"{algorithm} Credential={AK}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    # 最终请求头
    headers = {
        'Content-Type': ContentType,
        'X-Date': amz_date,
        'Authorization': authorization_header
    }

    # 打印最终请求头
    print("Headers:")
    print(headers)

    try:
        response = requests.post(endpoint, headers=headers, params=query_params, data=body)
        print("Response Status Code:", response.status_code)
        print("Response Headers:", response.headers)
        print("Response Body:", response.text)
        response.raise_for_status()
        res = response.json()
        if 'token' not in res:
            raise Exception(res.get('msg', '获取token失败'))
        token = res['token']
        expires_at = res.get('expires_at', 0)
        if expires_at == 0:
            # 如果响应中没有 expires_at，则手动计算
            expires_at = int(datetime.datetime.utcnow().timestamp()) + expiration
        save_token(token, expires_at)
        return token
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        try:
            print("Response Content:", response.json())
        except json.JSONDecodeError:
            print("Response Content:", response.text)
        raise
    except Exception as e:
        raise Exception(f"获取token失败: {e}")

if __name__ == "__main__":
    try:
        token = get_token()
        print("获取的 Token:", token)
    except Exception as e:
        print(e)