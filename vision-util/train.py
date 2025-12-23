# train.py
# ------------------------------------------------------------
from ultralytics import YOLO

def train_yolo():
    model = YOLO("yolov8n.pt")  # 사용할 가중치 모델 선택

    results = model.train(
        data='../yolov8/dataset/data.yaml',  # 데이터셋 경로
        epochs=150,
        imgsz=320,
        batch=8,
        project='yolov8',
        name='dataset',
        device=0,
        verbose=True,
        exist_ok=True,
        augment=False,
        workers=1
    )
    return results

if __name__ == '__main__':
    results = train_yolo()
    print("✅ 학습이 완료되었습니다.")
    print(results)