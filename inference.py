import sys
import os
from pathlib import Path
# 方法一：绝对路径导入（100%有效）
sys.path.insert(0, '/root/autodl-tmp/underwater-detection/yolov5')

# 方法二：相对路径导入（备用）
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir / 'yolov5'))

# 强制验证
print("当前Python路径:")
for p in sys.path:
    print(f" - {p}")

print("\nutils目录内容:")
print(os.listdir('utils'))

# 现在应该能成功导入
from utils.general import non_max_suppression
print("✅ 成功导入 non_max_suppression")
import cv2 
import torch 
import time
import numpy as np

from utils.general import non_max_suppression


# 模型和设备初始化
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
model = torch.jit.load('./yolov5/runs/train/v2_test/weights/best.torchscript', map_location=DEVICE)
model.eval()

# 类别配置
NAMES = ['holothurian', 'echinus', 'scallop', 'starfish']
COLORS = [(255,0,0), (0,255,0), (0,0,255), (255,255,0)]

def letterbox(im, new_shape=(640, 640), color=(114, 114, 114)):
    """
    保持比例的resize并添加灰边填充
    修复点：确保new_shape是元组/列表
    """
    # 确保new_shape是元组/列表
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)
    
    # 获取原始尺寸
    shape = im.shape[:2]  # [height, width]
    
    # 计算缩放比例
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    
    # 计算新尺寸(保持比例)
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    
    # 均分填充到两侧
    dw /= 2
    dh /= 2
    
    # 执行resize
    if shape[::-1] != new_unpad:
        im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    
    # 添加填充
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    im = cv2.copyMakeBorder(im, top, bottom, left, right, 
                          cv2.BORDER_CONSTANT, value=color)
    return im, (r, r), (dw, dh)

def scale_coords(img1_shape, coords, img0_shape):
    """坐标转换函数"""
    # 计算缩放比例
    gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
    pad = (img1_shape[1] - img0_shape[1] * gain) / 2, (img1_shape[0] - img0_shape[0] * gain) / 2
    
    coords[:, [0, 2]] -= pad[0]  # x padding
    coords[:, [1, 3]] -= pad[1]  # y padding
    coords[:, :4] /= gain
    
    # 边界保护
    coords[:, [0, 2]] = coords[:, [0, 2]].clip(0, img0_shape[1])
    coords[:, [1, 3]] = coords[:, [1, 3]].clip(0, img0_shape[0])
    return coords

@torch.no_grad()
def detect_image(img_bytes, conf_thres=0.25):
    """优化的检测函数"""
    try:
        # 1. 图像解码
        img_np = np.frombuffer(img_bytes, np.uint8)
        orig_img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        if orig_img is None:
            raise ValueError("无法解码图像数据")

        # 2. 保持比例的预处理（修复调用方式）
        img, ratio, (dw, dh) = letterbox(orig_img, new_shape=(640, 640))  # 确保传入元组
        
        # 3. 转换为tensor
        img = img.transpose((2, 0, 1))[::-1]  # BGR to RGB
        img = np.ascontiguousarray(img)
        img_tensor = torch.from_numpy(img).float().to(DEVICE) / 255.0
        img_tensor = img_tensor.unsqueeze(0)

        # 4. 模型推理
        t0 = time.time()
        pred = model(img_tensor)
        dt = time.time() - t0

        # 5. 处理输出
        if isinstance(pred, (list, tuple)):
            pred = pred[0]  # 取第一个输出
        
        # 6. 应用NMS
        pred = non_max_suppression(pred, conf_thres=conf_thres)
        
        result = []
        for det in pred:
            if len(det):
                # 转换坐标
                det[:, :4] = scale_coords(img.shape[1:], det[:, :4], orig_img.shape)
                
                for *xyxy, conf, cls in det:
                    x1, y1, x2, y2 = map(int, xyxy)
                    result.append({
                        'cls': int(cls),
                        'name': NAMES[int(cls)],
                        'conf': round(float(conf), 2),
                        'bbox': [x1, y1, x2, y2]
                    })
                    
                    # 绘制检测框
                    color = COLORS[int(cls)]
                    cv2.rectangle(orig_img, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(orig_img, 
                               f"{NAMES[int(cls)]} {conf:.2f}",
                               (x1, y1-10), 
                               cv2.FONT_HERSHEY_SIMPLEX,
                               0.6, color, 2)

        # 7. 编码结果图
        _, img_encoded = cv2.imencode('.jpg', orig_img)
        return result, img_encoded.tobytes(), dt

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"检测失败: {str(e)}")