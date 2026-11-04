# sxm Spark 智能迎宾机器人
智能机器人应用开发 期末项目
## ✨项目功能
- register_face_ros.py：人脸拍照注册脚本，采集VIP人脸图片
- encode_faces.py：读取人脸照片，提取特征，生成人脸特征库
- test_recognize.py：单独调试人脸识别，不控制底盘
- main_control.py：主程序，人脸跟随、陌生人警告、深度避障、WASD手动控制
- realtime_chat.py：语音监听ASR识别，语音查询天气，画面展示文字结果
> 说明：天气仅画面文字展示，暂未实现TTS喇叭朗读播报；人脸跟随仅横向转向，前进速度固定，人脸框大小调速为预留扩展功能

## 🛠环境依赖
- ROS Noetic
- OpenCV
- face_recognition
- pyrealsense2
- pyaudio
- requests

## 📂文件说明
