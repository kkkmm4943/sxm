#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import cv2
import os
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError

# 保存路径
save_dir = os.path.expanduser("~/spark_noetic/sxm_project/face_data")
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

name = input("请输入你的名字（英文）: ")
bridge = CvBridge()
capture_flag = False

def image_callback(msg):
    global capture_flag
    try:
        cv_image = bridge.imgmsg_to_cv2(msg, "bgr8")
    except CvBridgeError as e:
        print(e)
        return

    cv2.imshow("Camera", cv_image)
    key = cv2.waitKey(1) & 0xFF
    
    # 按 's' 键保存
    if key == ord('s'):
        img_path = os.path.join(save_dir, f"{name}.jpg")
        cv2.imwrite(img_path, cv_image)
        print(f"照片已保存到: {img_path}")
        capture_flag = True

    if key == ord('q'):
        rospy.signal_shutdown("用户退出")

if __name__ == '__main__':
    rospy.init_node('face_register_node', anonymous=True)
    # 注意：这里的话题名要和你启动的摄像头驱动话题一致
    image_sub = rospy.Subscriber("/camera/color/image_raw", Image, image_callback)
    rospy.spin()
    cv2.destroyAllWindows()