import face_recognition
import pickle
import os
import glob

# 路径设置（确保和你的文件夹结构一致）
data_dir = os.path.expanduser("~/spark_noetic/sxm_project/face_data")
encoding_file = os.path.join(data_dir, "faces.pkl")

known_encodings = []
known_names = []

# 遍历目录下所有 jpg 图片
for img_path in glob.glob(os.path.join(data_dir, "*.jpg")):
    # 从文件名提取名字（比如 suziying.jpg -> suziying）
    name = os.path.splitext(os.path.basename(img_path))[0]
    
    print(f"正在处理: {name} ...")
    # 加载图片并提取特征
    image = face_recognition.load_image_file(img_path)
    encodings = face_recognition.face_encodings(image)
    
    if len(encodings) > 0:
        known_encodings.append(encodings[0])
        known_names.append(name)
        print(f"  ✓ 成功提取 {name} 的特征")
    else:
        print(f"  ✗ 在 {name}.jpg 中未检测到人脸，请检查照片是否清晰！")

# 保存特征库
data = {"encodings": known_encodings, "names": known_names}
with open(encoding_file, "wb") as f:
    pickle.dump(data, f)

print(f"\n✅ 人脸特征库已保存: {encoding_file}")
print(f"共录入 {len(known_names)} 个人: {known_names}")