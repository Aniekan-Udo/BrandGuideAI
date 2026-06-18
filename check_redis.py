import redis
import json

r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
keys = r.keys('stream:*')
for k in keys:
    print(f"Key: {k}")
    items = r.lrange(k, 0, -1)
    for i, item in enumerate(items[-5:]): # just last 5
        print(f"[{i}]: {item[:200]}...")
