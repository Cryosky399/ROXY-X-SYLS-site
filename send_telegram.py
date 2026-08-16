import sys
import json
import urllib.request
import urllib.error

TOKEN = "8684264908:AAE9FzHZH6LKG6hri8XJdsOvXMwqYlK0I_o"
APK_PATH = "/root/skybots-patcher-app.apk"
ZIP_PATH = "/root/skybots-server-code.zip"

def make_request(url, data=None, headers=None):
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read()
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def main():
    print("Checking updates to find Chat ID...")
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    res = make_request(url)
    if not res:
        print("Failed to contact Telegram API. Internet access might be blocked.")
        sys.exit(1)
        
    try:
        data = json.loads(res.decode('utf-8'))
    except Exception as e:
        print("Failed to parse JSON response:", e)
        sys.exit(1)
        
    results = data.get("result", [])
    if not results:
        print("No updates found. Please send a message to your Telegram Bot first so it can get your Chat ID!")
        sys.exit(1)
        
    # Get the chat ID of the most recent message
    last_msg = results[-1]
    chat_id = None
    if "message" in last_msg:
        chat_id = last_msg["message"]["chat"]["id"]
    elif "my_chat_member" in last_msg:
        chat_id = last_msg["my_chat_member"]["chat"]["id"]
        
    if not chat_id:
        print("Could not find Chat ID in the updates.")
        sys.exit(1)
        
    print(f"Found Chat ID: {chat_id}. Sending files...")
    
    # Send APK
    send_doc_url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    
    def send_file(file_path, file_name):
        boundary = '----TelegramFormBoundary'
        parts = []
        parts.append(f'--{boundary}')
        parts.append(f'Content-Disposition: form-data; name="chat_id"')
        parts.append('')
        parts.append(str(chat_id))
        
        parts.append(f'--{boundary}')
        with open(file_path, 'rb') as f:
            file_content = f.read()
            
        parts.append(f'Content-Disposition: form-data; name="document"; filename="{file_name}"')
        parts.append('Content-Type: application/octet-stream')
        parts.append('')
        parts.append(file_content)
        parts.append(f'--{boundary}--')
        
        # Combine parts into bytes
        body = bytearray()
        for p in parts:
            if isinstance(p, str):
                body.extend((p + '\r\n').encode('utf-8'))
            else:
                body.extend(p)
                body.extend(b'\r\n')
                
        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(body))
        }
        
        req_res = make_request(send_doc_url, data=body, headers=headers)
        if req_res:
            print(f"✅ {file_name} sent successfully!")
        else:
            print(f"❌ Failed to send {file_name}")
            
    send_file(APK_PATH, "skybots-patcher-app.apk")
    send_file(ZIP_PATH, "skybots-server-code.zip")

if __name__ == "__main__":
    main()
