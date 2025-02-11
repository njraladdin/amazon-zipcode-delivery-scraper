import requests
cookies = {
   # "aws-userInfo-signed": "eyJ0eXAiOiJKV1MiLCJrZXlSZWdpb24iOiJ1cy1lYXN0LTEiLCJhbGciOiJFUzM4NCIsImtpZCI6ImRmMDYyMjgyLTE4OGUtNDdmYi1hNjc1LThiYjllYWNhMzc3NCJ9.eyJzdWIiOiIiLCJzaWduaW5UeXBlIjoiUFVCTElDIiwiaXNzIjoiaHR0cDpcL1wvc2lnbmluLmF3cy5hbWF6b24uY29tXC9zaWduaW4iLCJrZXliYXNlIjoiYU5QSmdtRHlQdDhuRUVPTktyUE43am43TlJvK1lOaCtzd3hYY0dMeVgrUT0iLCJhcm4iOiJhcm46YXdzOmlhbTo6MDgwNTU0MTA3NzM3OnJvb3QiLCJ1c2VybmFtZSI6IkFsYWRkaW4lMjBOYWpqYXIifQ.KvvoThaPrJmocArFRgyz3HuVvOklAgY7xc9w6i5lA1eSxThoqVdA_cqJWALxv3zBCyVawis7IyTJA2OdYD8KjJq7Yca1W0Ym7cRwMpxs8EphKVL-FQ2iSL2m5DYRpn69",
   # "aws-userInfo": "%7B%22arn%22%3A%22arn%3Aaws%3Aiam%3A%3A080554107737%3Aroot%22%2C%22alias%22%3A%22%22%2C%22username%22%3A%22Aladdin%2520Najjar%22%2C%22keybase%22%3A%22aNPJgmDyPt8nEEONKrPN7jn7NRo%2BYNh%2BswxXcGLyX%2BQ%5Cu003d%22%2C%22issuer%22%3A%22http%3A%2F%2Fsignin.aws.amazon.com%2Fsignin%22%2C%22signinType%22%3A%22PUBLIC%22%7D",
   # "session-id-time": "2082787201l",
    "i18n-prefs": "USD",
    "ubid-main": "130-9691885-0543905",
    "session-id": "130-9174360-5337210",
#    "sp-cdn": "L5Z9:TN",
   # "session-token": "CkPsZSG8GrKblyoBYRH26vyW9E+mfyYFZso2qmMb37o1VwycbmlQSfWHVqe2LFtisCi1h8ccqpJQ5Zbq9RFABCAWXwfgdO8WW/5GYx/i9DCfx/+2zsKufbhBT54Er0QjS/B8Q2AYYVuFxky7UxCWcO8By4TEerAAphTxs7FSKGwYhCMzOMyaxrXMsFY6q+TyQ3QyI/r9Xiq3R5tbvekKb8y6VBxh6fGxwSfJUSMyvEJSRcS5PZN/Srb6azQHQZqG9U1DIEITO3zyBs/o6R8xhGK9CIX/jvM8OjXQrwdF1viGIN9N8+/rwNum7fm5pTOFKMT/1sERToR7EYbYUtHymp231et9hofi",
   # "csm-hit": "tb:9SZ488YMWY2JAT3YH6WP+s-W35B6HCW9YCY2DGGMBET|1738147654784&t:1738147654784&adb:adblk_no"
}

url = "https://www.amazon.com/portal-migration/hz/glow/get-rendered-address-selections?deviceType=desktop&pageType=Detail&storeContext=photo&actionSource=desktop-modal"
cookie_string = "; ".join([f"{key}={value}" for key, value in cookies.items()])

payload = {}
headers = {
  'accept': 'text/html,*/*',
  'accept-language': 'en-US,en;q=0.9,be;q=0.8,ar;q=0.7',
  'anti-csrftoken-a2z': 'hLPVKba/voGL37sM7crTemlPzBm68WWerq/IjcHnW9piAAAAAGeaSVEAAAAB',
  'cookie': cookie_string,
  'device-memory': '8',
  'dnt': '1',
  'downlink': '7.9',
  'dpr': '1',
  'ect': '4g',
  'priority': 'u=1, i',
  'referer': 'https://www.amazon.com/GoPro-HERO9-Black-Waterproof-Stabilization/dp/B08DK5ZH44',
  'rtt': '200',
  'sec-ch-device-memory': '8',
  'sec-ch-dpr': '1',
  'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
  'sec-ch-ua-mobile': '?0',
  'sec-ch-ua-platform': '"Windows"',
  'sec-ch-ua-platform-version': '"15.0.0"',
  'sec-ch-viewport-width': '1120',
  'sec-fetch-dest': 'empty',
  'sec-fetch-mode': 'cors',
  'sec-fetch-site': 'same-origin',
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
  'viewport-width': '1120',
  'x-requested-with': 'XMLHttpRequest',
  #'Authorization': 'Basic e3tnZW9ub2RlX2FwaV91c2VybmFtZX19Ont7Z2Vvbm9kZV9hcGlfcGFzc3dvcmR9fQ=='
}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)
# Save raw response to test.html file
with open('test.html', 'w', encoding='utf-8') as f:
    f.write(response.text)

