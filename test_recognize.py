#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import cv2
import pickle
import os
import face_recognition
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import numpy as np

# 加载特征库
encoding_file = os.path.expanduser("~/spark_noetic/sxm_project/face_data/faces.pkl")
with open(encoding_file, "rb") as f:
    data = pickle.load(f)

bridge = CvBridge()

def image_callback(msg):
    try:
        frame = bridge.imgmsg_to_cv2(msg, "bgr8")
    except Exception as e:
        print(e)
        return

    # 缩小图像加速处理（1/4大小）
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    rgb_small = np.ascontiguousarray(rgb_small)# BGR 转 RGB

    # 检测人脸位置并提取特征
    face_locations = face_recognition.face_locations(rgb_small)
    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        # 与已知人脸比对
        matches = face_recognition.compare_faces(data["encodings"], face_encoding, tolerance=0.5)
        name = "Unknown"

        if True in matches:
            first_match_index = matches.index(True)
            name = data["names"][first_match_index]

        # 画框并标注名字（坐标放大回原图尺寸）
        top *= 4; right *= 4; bottom *= 4; left *= 4
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

    cv2.imshow("Face Recognition Test", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        rospy.signal_shutdown("Quit")

if __name__ == '__main__':
    rospy.init_node('face_test_node', anonymous=True)
    # 注意：话题名请根据你实际启动的摄像头驱动话题修改
    rospy.Subscriber("/camera/color/image_raw", Image, image_callback)
    rospy.spin()
    cv2.destroyAllWindows()