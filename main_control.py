#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import cv2
import pickle
import os
import time
import struct
import threading
import numpy as np
import face_recognition
import requests
import re
import pyaudio
import wave
from aip import AipSpeech
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
from cv_bridge import CvBridge

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
SILENCE_THRESHOLD = 600      
SILENCE_DURATION = 1.0       
MAX_RECORD_SECONDS = 8

class SparkWelcomeRobot:
    def __init__(self):
        rospy.init_node('spark_welcome_robot')
        
        # 1. 加载人脸特征库
        encoding_file = os.path.expanduser("~/spark_noetic/sxm_project/face_data/faces.pkl")
        with open(encoding_file, "rb") as f:
            self.data = pickle.load(f)
        
        self.bridge = CvBridge()
        self.cmd_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        
        # 2. 状态变量初始化
        self.current_state = "IDLE" 
        self.last_state = "IDLE"    
        self.obstacle_detected = False
        self.safe_distance = 0.6    # 🌟 深度图避障安全距离（米），建议0.5-0.8之间
        self.is_following = False 
        
        # 天气显示变量
        self.weather_display_text = ""
        self.weather_display_time = 0
        
        # WASD 键盘控制变量
        self.last_key_time = 0
        self.keyboard_linear = 0.0
        self.keyboard_angular = 0.0
        
        # 3. 订阅话题
        rospy.Subscriber("/camera/color/image_raw", Image, self.image_callback)
        # 🌟 把雷达订阅换成深度图订阅（用对齐后的深度图，更准）
        rospy.Subscriber("/camera/aligned_depth_to_color/image_raw", Image, self.depth_callback)
        
        # 4. 启动语音监听子线程
        self.voice_thread = threading.Thread(target=self.voice_listener_loop)
        self.voice_thread.daemon = True 
        self.voice_thread.start()
        
        rospy.loginfo("机器人已启动！(视觉跟随+深度避障+语音天气+WASD控制)")

    # ================= 深度图避障部分 =================
    def depth_callback(self, msg):
        """深度图回调：只看画面正中间区域，测距避障"""
        try:
            # 接收 16UC1 格式的深度图（单位是毫米）
            depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="16UC1")
            
            h, w = depth_image.shape
            
            # 🌟 提取画面正中间 100x100 的区域（代表正前方）
            center_roi = depth_image[h//2 - 50 : h//2 + 50, w//2 - 50 : w//2 + 50]
            
            # 过滤掉无效值（0表示测不到距离，比如太近或玻璃）
            valid_depths = center_roi[center_roi > 0]
            
            if len(valid_depths) > 0:
                min_dist_mm = np.min(valid_depths)
                min_dist_m = min_dist_mm / 1000.0 # 毫米转米
                
                # 打印调试信息
                rospy.loginfo_throttle(1.0, f"👀 视觉避障-正前方距离: {min_dist_m:.2f} 米")
                
                if min_dist_m < self.safe_distance:
                    self.obstacle_detected = True
                else:
                    self.obstacle_detected = False
            else:
                # 如果正前方测不到深度（全黑或太近），为了防止撞上，直接当做有障碍物
                self.obstacle_detected = True
                
        except Exception as e:
            rospy.logerr(f"深度图解析失败: {e}")

    # ================= 语音与天气处理部分 =================
    def record_until_silence(self):
        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=FORMAT, channels=CHANNELS,
                            rate=RATE, input=True, frames_per_buffer=CHUNK)
        except Exception as e:
            return None

        frames = []
        recording = False
        silent_chunks = 0
        max_silent_chunks = int(RATE / CHUNK * SILENCE_DURATION)
        max_chunks = int(RATE / CHUNK * MAX_RECORD_SECONDS)

        while not rospy.is_shutdown():
            data = stream.read(CHUNK, exception_on_overflow=False)
            shorts = struct.unpack('<' + 'h' * CHUNK, data)
            amplitude = max(abs(s) for s in shorts) if shorts else 0

            if amplitude > SILENCE_THRESHOLD:
                if not recording:
                    print("\n🎤 检测到说话，开始录音...")
                    recording = True
                frames.append(data)
                silent_chunks = 0
            elif recording:
                frames.append(data)
                silent_chunks += 1
                if silent_chunks > max_silent_chunks:
                    break
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
        return filename

    def recognize_audio(self, file_path):
        with open(file_path, 'rb') as f:
            audio_data = f.read()
        result = client.asr(audio_data, 'wav', 16000, {'dev_pid': 1537})
        if result['err_no'] == 0:
            return result['result'][0]
        return None

    def query_weather(self, text):
        headers = {'Accept-Encoding': 'gzip, deflate'}
        keywords_to_remove = ["帮我查一下", "查一下", "查查", "今天", "明天", "现在", "的", "天气", "怎么样", "如何", "是多少", "是什么", "情况"]
        city_name = text
        for word in keywords_to_remove:
            city_name = city_name.replace(word, "")
        city_name = re.sub(r'[^\w\s]', '', city_name).strip()
        
        if not city_name:
            return "请问你要查询哪个城市的天气？"

        geo_url = f"https://{QWEATHER_API_HOST}/geo/v2/city/lookup"
        geo_params = {'key': QWEATHER_API_KEY, 'location': city_name, 'number': 1}
        
        try:
            geo_resp = requests.get(geo_url, params=geo_params, headers=headers, timeout=5)
            geo_data = geo_resp.json()
            if geo_data.get('code') != '200' or not geo_data.get('location'):
                return f"抱歉，我没找到「{city_name}」这个地方。"
            location_id = geo_data['location'][0]['id']
            city_display = geo_data['location'][0]['name']
        except Exception as e:
            return f"地名解析出错。"

        weather_url = f"https://{QWEATHER_API_HOST}/v7/weather/now"
        weather_params = {'key': QWEATHER_API_KEY, 'location': location_id, 'lang': 'zh'}
        
        try:
            resp = requests.get(weather_url, params=weather_params, headers=headers, timeout=5)
            data = resp.json()
            if data.get('code') == '200':
                now = data['now']
                return f"{city_display}当前{now['text']}，温度{now['temp']}°C，湿度{now['humidity']}%。"
            else:
                return f"天气数据获取失败。"
        except Exception as e:
            return f"天气查询出错。"

    def voice_listener_loop(self):
        print("🎤 语音监听线程已启动，说包含“天气”的话即可查询。")
        while not rospy.is_shutdown():
            try:
                audio_file = self.record_until_silence()
                if not audio_file:
                    continue
                
                text = self.recognize_audio(audio_file)
                if not text:
                    continue
                    
                print(f"\n🗣️ 你说：{text}")
                if '天气' in text:
                    reply = self.query_weather(text)
                    print(f"🤖 机器人：{reply}")
                    self.weather_display_text = reply
                    self.weather_display_time = time.time()
                else:
                    print("🤖 机器人：我听到了，可以说“北京天气”来查询。")
            except Exception as e:
                time.sleep(1) 

    def print_welcome(self):
        rospy.loginfo("\033[92m" + "="*40 + "\033[0m")
        rospy.loginfo("\033[92m🎙️  [状态]：VIP识别成功，开始跟随！\033[0m")
        rospy.loginfo("\033[92m" + "="*40 + "\033[0m")

    def print_warning(self):
        rospy.logwarn("\033[91m" + "="*40 + "\033[0m")
        rospy.logwarn("\033[91m🛑 [状态]：未识别成功，请留步！\033[0m")
        rospy.logwarn("\033[91m" + "="*40 + "\033[0m")

    def image_callback(self, msg):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            return

        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        rgb_small = np.ascontiguousarray(rgb_small)

        face_locations = face_recognition.face_locations(rgb_small)
        face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

        target_face_x = None
        target_face_area = 0
        detected_vip = False
        detected_unknown = False

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            matches = face_recognition.compare_faces(self.data["encodings"], face_encoding, tolerance=0.5)
            name = "Unknown"
            
            if True in matches:
                first_match_index = matches.index(True)
                name = self.data["names"][first_match_index]

            top *= 4; right *= 4; bottom *= 4; left *= 4
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

            if name != "Unknown":
                detected_vip = True
                area = (right - left) * (bottom - top)
                if area > target_face_area:
                    target_face_area = area
                    target_face_x = (left + right) // 2
            else:
                detected_unknown = True

        # 状态机决策
        if detected_vip:
            self.is_following = True
            self.current_state = "FOLLOW"
        elif len(face_locations) > 0 and self.is_following:
            self.current_state = "FOLLOW"
            if target_face_x is None and len(face_locations) > 0:
                 (t, r, b, l) = face_locations[0]
                 target_face_x = ((l + r) // 2) * 4
        elif detected_unknown and not self.is_following:
            self.current_state = "WARNING"
        else:
            self.is_following = False
            self.current_state = "IDLE"

        if self.current_state != self.last_state:
            if self.current_state == "FOLLOW" and self.last_state != "FOLLOW":
                self.print_welcome()
            elif self.current_state == "WARNING":
                self.print_warning()
            self.last_state = self.current_state

        # 天气显示
        if time.time() - self.weather_display_time < 5.0 and self.weather_display_text:
            overlay = frame.copy()
            cv2.rectangle(overlay, (10, 10), (650, 60), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
            cv2.putText(frame, self.weather_display_text, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # 画面提示文字
        if self.current_state == "IDLE":
             cv2.putText(frame, "[Manual Control] W/A/S/D to Move, Space to Stop", (20, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # 🌟 在画面上画出深度避障的检测框（正中间 100x100 区域）
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (w//2 - 50, h//2 - 50), (w//2 + 50, h//2 + 50), (0, 165, 255), 2)
        if self.obstacle_detected:
             cv2.putText(frame, "WARNING: OBSTACLE AHEAD!", (w//2 - 150, h//2 - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imshow("Spark Welcome Robot", frame)
        
        key = cv2.waitKey(1) & 0xFF
        self.handle_keyboard(key)
        
        self.execute_control(target_face_x, frame.shape[1])

    def handle_keyboard(self, key):
        if self.current_state == "IDLE":
            if key == ord('w'): 
                self.keyboard_linear = 0.2
                self.keyboard_angular = 0.0
                self.last_key_time = time.time()
            elif key == ord('s'): 
                self.keyboard_linear = -0.2
                self.keyboard_angular = 0.0
                self.last_key_time = time.time()
            elif key == ord('a'): 
                self.keyboard_linear = 0.0
                self.keyboard_angular = 0.5
                self.last_key_time = time.time()
            elif key == ord('d'): 
                self.keyboard_linear = 0.0
                self.keyboard_angular = -0.5
                self.last_key_time = time.time()
            elif key == ord(' '): 
                self.keyboard_linear = 0.0
                self.keyboard_angular = 0.0
                self.last_key_time = time.time()

    def execute_control(self, face_x, frame_width):
        cmd = Twist()
        
        # 1. 避障优先级最高
        if self.obstacle_detected:
            cmd.linear.x = 0.0
            cmd.angular.z = 0.0
            rospy.logwarn_throttle(2.0, "⚠️ 前方有障碍物，强制刹车！")
            self.cmd_pub.publish(cmd)
            return

        # 2. 自动状态控制
        if self.current_state == "WARNING":
            cmd.linear.x = 0.0
            cmd.angular.z = 0.0
            self.cmd_pub.publish(cmd)
            return
            
        elif self.current_state == "FOLLOW":
            center_x = frame_width / 2
            if face_x is not None:
                if face_x < center_x - 100:    
                    cmd.angular.z = 0.3        
                elif face_x > center_x + 100:  
                    cmd.angular.z = -0.3       
                else:                          
                    cmd.angular.z = 0.0
                cmd.linear.x = 0.15 
            self.cmd_pub.publish(cmd)
            return

        # 3. IDLE 状态：键盘控制逻辑
        if self.current_state == "IDLE":
            if time.time() - self.last_key_time > 0.3:
                self.keyboard_linear = 0.0
                self.keyboard_angular = 0.0
            
            cmd.linear.x = self.keyboard_linear
            cmd.angular.z = self.keyboard_angular
            self.cmd_pub.publish(cmd)

if __name__ == '__main__':
    try:
        robot = SparkWelcomeRobot()
        rospy.spin() 
    except rospy.ROSInterruptException:
        pass