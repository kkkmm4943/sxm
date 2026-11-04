import pyaudio
import wave
import os
import requests
import re
import time
import struct
from aip import AipSpeech

# ========== 百度语音识别配置 ==========
APP_ID = '124416906'
API_KEY = 'Fr5XytULgLXQbtiMpNOT3L4O'
SECRET_KEY = 'RJBlHgWSwEAnxsMuV9XI2sBX5h7YYEHp'
client = AipSpeech(APP_ID, API_KEY, SECRET_KEY)

# ========== 和风天气配置 ==========
QWEATHER_API_KEY = '1438eed5765843988512ad26a7fcfc3b'
QWEATHER_API_HOST = 'my2tuq8na3.re.qweatherapi.com'

# ========== 音频参数 ==========
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
SILENCE_THRESHOLD = 500      # 音量阈值，环境嘈杂时调大
SILENCE_DURATION = 1.2       # 静音多久算说完（秒）
MAX_RECORD_SECONDS = 10      # 单次最长录音时间


def record_until_silence():
    """监听麦克风，检测到说话后录音，静音后返回音频文件路径"""
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True, frames_per_buffer=CHUNK)

    print("🎤 监听中...（说话即可）")
    frames = []
    recording = False
    silent_chunks = 0
    max_silent_chunks = int(RATE / CHUNK * SILENCE_DURATION)
    max_chunks = int(RATE / CHUNK * MAX_RECORD_SECONDS)

    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        # 计算当前块的最大振幅
        shorts = struct.unpack('<' + 'h' * CHUNK, data)
        amplitude = max(abs(s) for s in shorts) if shorts else 0

        if amplitude > SILENCE_THRESHOLD:
            if not recording:
                print("🔴 检测到说话，开始录音...")
                recording = True
            frames.append(data)
            silent_chunks = 0
        elif recording:
            frames.append(data)
            silent_chunks += 1
            if silent_chunks > max_silent_chunks:
                break
        # 防止录太长
        if len(frames) > max_chunks:
            break

    stream.stop_stream()
    stream.close()
    p.terminate()

    if not frames:
        return None

    filename = '/tmp/realtime_input.wav'
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    print("✅ 录音结束")
    return filename


def recognize(file_path):
    """百度短语音识别"""
    with open(file_path, 'rb') as f:
        audio_data = f.read()
    result = client.asr(audio_data, 'wav', 16000, {'dev_pid': 1537})
    if result['err_no'] == 0:
        return result['result'][0]
    return None


def query_weather(text):
    """
    直接从用户说的话里提取地名并查询天气
    例如："江门天气怎么样" -> 提取 "江门"
    """
    headers = {
        'Accept-Encoding': 'gzip, deflate'
    }
    
    # 1. 文本清洗：去掉口语化的废话，提取核心地名
    keywords_to_remove = [
        "帮我查一下", "查一下", "查查", "今天", "明天", "现在", "的",
        "天气", "怎么样", "如何", "是多少", "是什么", "情况"
    ]
    city_name = text
    for word in keywords_to_remove:
        city_name = city_name.replace(word, "")
    
    # 去掉标点符号和空格
    city_name = re.sub(r'[^\w\s]', '', city_name).strip()
    
    if not city_name:
        return "请问你要查询哪个城市的天气？"

    # 2. 第一步：把提取出的地名丢给 GeoAPI 查 Location ID
    geo_url = f"https://{QWEATHER_API_HOST}/geo/v2/city/lookup"
    geo_params = {'key': QWEATHER_API_KEY, 'location': city_name, 'number': 1}
    
    try:
        geo_resp = requests.get(geo_url, params=geo_params, headers=headers, timeout=5)
        geo_data = geo_resp.json()
        
        # 如果查不到这个地名，直接返回提示
        if geo_data.get('code') != '200' or not geo_data.get('location'):
            return f"抱歉，我没找到「{city_name}」这个地方，请再说一遍地名。"
        
        # 获取和风标准的 Location ID 和 官方名称
        location_id = geo_data['location'][0]['id']
        city_display = geo_data['location'][0]['name']
    except Exception as e:
        return f"地名解析出错：{e}"

    # 3. 第二步：用 Location ID 查实时天气
    weather_url = f"https://{QWEATHER_API_HOST}/v7/weather/now"
    weather_params = {'key': QWEATHER_API_KEY, 'location': location_id, 'lang': 'zh'}
    
    try:
        resp = requests.get(weather_url, params=weather_params, headers=headers, timeout=5)
        data = resp.json()
        
        if data.get('code') == '200':
            now = data['now']
            return f"{city_display}当前{now['text']}，温度{now['temp']}°C，湿度{now['humidity']}%。"
        else:
            return f"天气数据获取失败，错误码：{data.get('code')}"
    except Exception as e:
        return f"天气查询出错：{e}"


if __name__ == '__main__':
    print("🤖 实时语音助手已启动，说“XX天气”即可查询")
    while True:
        try:
            audio_file = record_until_silence()
            if not audio_file:
                continue
                
            text = recognize(audio_file)
            if not text:
                print("❌ 识别失败，请再说一次")
                continue
                
            print(f"🗣️ 你说：{text}")

            # 如果话里包含“天气”，就进入天气查询流程
            if '天气' in text:
                reply = query_weather(text)
                print(f"🤖 机器人：{reply}")
            else:
                print("🤖 机器人：我听到了，可以说“北京天气”或“江门天气”来查询。")
                
        except KeyboardInterrupt:
            print("\n👋 程序已退出")
            break
        except Exception as e:
            print(f"⚠️ 运行出错：{e}")
            # 稍微等一下，防止死循环刷屏
            time.sleep(1)