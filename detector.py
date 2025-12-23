# detector.py
# ------------------------------------------------------------
from __future__ import annotations

from ultralytics import YOLO
import cv2
import threading
from queue import Queue
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Callable, Dict


# ----------------------------------------
# 설정
# ----------------------------------------
model_path = "./yolov8/dataset/weights/best.pt"
# 카메라별 Good / Bad 기준
good_prod0 = ["Orange_Waper"]
bad_prod0  = ["Brown_Waper"]

good_prod1 = ["Square"]
bad_prod1  = ["Not_Square"]


# ============================================================
#  CameraStream — 카메라 프레임 수집
# ============================================================
class CameraStream:
    def __init__(self, camera_ids, width=640, height=480):
        self.camera_ids = camera_ids
        self.queues = {cid: Queue(maxsize=1) for cid in camera_ids}
        self.captures = {cid: cv2.VideoCapture(cid) for cid in camera_ids}
        self.running = False

        for _, cap in self.captures.items():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def _reader(self, cam_id: int):
        cap = self.captures[cam_id]
        q = self.queues[cam_id]

        while self.running:
            ret, frame = cap.read()
            if not ret:
                continue

            if q.full():
                q.get()
            q.put(frame)

        cap.release()

    def start(self):
        self.running = True
        self.threads = []
        for cam_id in self.camera_ids:
            t = threading.Thread(target=self._reader, args=(cam_id,), daemon=True)
            t.start()
            self.threads.append(t)

    def stop(self):
        self.running = False

    def get_frame(self, cam_id: int):
        q = self.queues[cam_id]
        return q.get() if not q.empty() else None


# ============================================================
# 데이터 구조
# ============================================================
@dataclass
class DetectionResult:
    timestamp: datetime
    object_id: int
    is_defective: bool
    confidence_avg: float
    frame_count: int

    def to_dict(self):
        return {
            "timestamp": self.timestamp.isoformat(),
            "object_id": self.object_id,
            "defective": self.is_defective,
            "confidence": round(self.confidence_avg, 3),
            "frames": self.frame_count
        }
  

@dataclass
class TrackedObject:
    object_id: int
    bbox: tuple
    good_list: List[str]  # VisionAI에서 camera별 기준을 받아 저장
    
    is_good: bool = None
    detections: List[tuple] = field(default_factory=list)
    frame_count: int = 0
    missing_time: int = 0
    in_roi: bool = False
    finalized: bool = False
    finalized_frame_count: int = 0
    display_duration: int = 100

    def add_missing(self):
        self.missing_time += 1

    def clear_missing(self):
        self.missing_time = 0

    def add_detection(self, cls: str, conf: float):
        self.detections.append((cls, conf))
        self.frame_count += 1

    def get_final_decision(self) -> tuple[bool, float] | None:
        # 감지 데이터 부족
        if len(self.detections) < 15:
            return None

        # good_score / bad_score 계산을 camera 기준 good_list로만 수행
        good_score = sum(c for cls, c in self.detections if cls in self.good_list)
        total_score = sum(c for _, c in self.detections)

        if total_score == 0:
            return None

        # is_good 판정 (예: good_score 비율 기반)
        self.is_good = (good_score / total_score) >= 0.7

        avg_conf = total_score / len(self.detections)

        return self.is_good, avg_conf


# ============================================================
# 시작 신호 + (bool)->void 콜백 관리
# ============================================================
class DetectionSignalController:
    """
    - request_start() : 상위 공정에서 '검출 시작' 신호가 들어올 때 호출
    - set_result_callback(cb) : cb(bool) 형태로 PLC 등에 보낼 콜백 등록
    - handle_detection(is_good) : VisionAI에서 finalize 시 호출
    """
    def __init__(self, name: str = ""):
        self.name = name
        self._armed: bool = False
        self._result_callback: Callable[[bool], None] | None = None

    def request_start(self) -> None:
        """
        상위 공정이 완료되어 다음 검출 1회를 허용할 때 호출.
        다음 finalize 결과 1회만 통과시키고 다시 disarm 된다.
        """
        print("detector.py:Request confirmed")
        self._armed = True

    def set_result_callback(self, cb: Callable[[bool], None]) -> None:
        """
        cb: (is_good: bool) -> None
        """
        self._result_callback = cb

    def handle_detection(self, is_good: bool) -> None:
        """
        VisionAI에서 finalize될 때 호출.
        _armed 상태가 아니면 무시, _armed이면 cb를 1번 호출하고 disarm.
        """
        if not self._armed:
            return
        self._armed = False
        if self._result_callback is not None:
            self._result_callback(is_good)


# ============================================================
# VisionAI — 카메라별 독립 추적/판정 엔진
# ============================================================
class VisionAI:
    def __init__(self, model_path:str, good_list:List[str], bad_list:List[str],
                 roi_center_ratio:float=0.5, roi_width_ratio:float=0.6, roi_height_ratio:float=0.4):
        self.model = YOLO(model_path)
        self.callbacks: List[Callable[[DetectionResult], None]] = []
        self.tracked_objects: Dict[int, TrackedObject] = {}
        self.next_object_id = 0
        
        self.good_list = good_list
        self.bad_list = bad_list

        self.roi_center_ratio = roi_center_ratio
        self.roi_width_ratio = roi_width_ratio
        self.roi_height_ratio = roi_height_ratio
        self.roi: tuple[int, int, int, int] | None = None

        self.max_missing_times = 30
        self.min_frames_for_decision = 10
        self.iou_threshold = 0.3

        self.frame_width: int | None = None
        self.frame_height: int | None = None

    def register_callback(self, fn: Callable[[DetectionResult], None]) -> None:
        self.callbacks.append(fn)

    def _setup_roi(self, w: int, h: int) -> None:
        rw = int(w * self.roi_width_ratio)
        rh = int(h * self.roi_height_ratio)
        cx = int(w * self.roi_center_ratio)
        cy = int(h * 0.5)
        x1 = max(0, cx - rw // 2)
        x2 = min(w, cx + rw // 2)
        y1 = max(0, cy - rh // 2)
        y2 = min(h, cy + rh // 2)
        self.roi = (x1, y1, x2, y2)

    def _is_outside_frame(self, obj: TrackedObject) -> bool:
        x1, y1, x2, y2 = obj.bbox
        if x2 < 0:
            return True
        if x1 > self.frame_width:
            return True
        if y2 < 0:
            return True
        if y1 > self.frame_height:
            return True
        return False

    def _calculate_iou(self, b1, b2) -> float:
        x1, y1, x2, y2 = b1
        X1, Y1, X2, Y2 = b2
        inter_x1 = max(x1, X1)
        inter_y1 = max(y1, Y1)
        inter_x2 = min(x2, X2)
        inter_y2 = min(y2, Y2)

        if inter_x2 < inter_x1 or inter_y2 < inter_y1:
            return 0.0

        inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area1 = (x2 - x1) * (y2 - y1)
        area2 = (X2 - X1) * (Y2 - Y1)
        return inter / (area1 + area2 - inter)

    def _is_in_roi(self, box) -> bool:
        if not self.roi:
            return False
        x1, y1, x2, y2 = box
        rx1, _, rx2, _ = self.roi
        cx = (x1 + x2) / 2
        return rx1 <= cx <= rx2

    # ============================================================
    # 트래킹 업데이트
    # ============================================================
    def _update_tracks(self, detections, out_list: List[bool]) -> None:
        matched: set[int] = set()
        to_remove: List[int] = []

        # 모든 객체 missing 증가 (finalized 포함)
        for obj in self.tracked_objects.values():
            obj.add_missing()

        # IOU 매칭 (finalized 포함, bbox 업데이트용)
        for bbox, cls, conf in detections:
            best_id = None
            best_iou = self.iou_threshold

            for oid, obj in self.tracked_objects.items():
                iou = self._calculate_iou(obj.bbox, bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_id = oid

            if best_id is not None:
                obj = self.tracked_objects[best_id]
                obj.clear_missing()
                obj.bbox = bbox

                if not obj.finalized:
                    obj.add_detection(cls, conf)
                    obj.in_roi = self._is_in_roi(bbox)

                matched.add(best_id)
            else:
                new_obj = TrackedObject(self.next_object_id, bbox, self.good_list)
                new_obj.add_detection(cls, conf)
                new_obj.in_roi = self._is_in_roi(bbox)
                self.tracked_objects[self.next_object_id] = new_obj
                matched.add(self.next_object_id)
                self.next_object_id += 1

        # 삭제 / finalize 처리
        for oid, obj in list(self.tracked_objects.items()):

            # finalized 객체: 화면 밖이면 삭제
            if obj.finalized and self._is_outside_frame(obj):
                to_remove.append(oid)
                continue

            # finalized 객체: 일정 시간 이상 미검출 시 삭제
            if obj.missing_time > self.max_missing_times:
                to_remove.append(oid)
                continue

            # 비-finalized: 짧게 감지되었다가 사라지면 삭제
            if (not obj.finalized) and obj.frame_count < self.min_frames_for_decision and oid not in matched:
                to_remove.append(oid)
                continue

            # 비-finalized: 오래 미검출이면 삭제
            if (not obj.finalized) and oid not in matched and obj.missing_time > self.max_missing_times:
                to_remove.append(oid)
                continue

            # ROI 내부 + 프레임 수 충족 + 아직 finalize 안 됨 → 단 한 번 finalize
            if (not obj.finalized) and obj.in_roi and obj.frame_count >= self.min_frames_for_decision:
                self._finalize(obj, out_list)

        for oid in to_remove:
            del self.tracked_objects[oid]

    def _finalize(self, obj: TrackedObject, out_list: List[bool]) -> None:
        if obj.finalized:
            return

        decision = obj.get_final_decision()
        if not decision:
            return

        is_good, avg_conf = decision
        is_def = not is_good
        
        result = DetectionResult(
            timestamp=datetime.now(),
            object_id=obj.object_id,
            is_defective=is_def,
            confidence_avg=avg_conf,
            frame_count=obj.frame_count
        )

        obj.finalized = True

        # 내부용 bool 결과 (True = Good, False = Bad)
        out_list.append(is_good)

        # 상위 콜백들 호출 (DetectionResult 단위)
        for cb in self.callbacks:
            try:
                cb(result)
            except Exception as e:
                print(f"Vision callback error: {e}")

    # ============================================================
    # 그래픽 표시
    # ============================================================
    def _draw_roi(self, frame):
        if self.roi:
            x1, y1, x2, y2 = self.roi
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
        return frame

    def _draw_tracks(self, frame):
        for oid, obj in self.tracked_objects.items():
            x1, y1, x2, y2 = map(int, obj.bbox)

            if obj.finalized:
                color = (0, 255, 0) if obj.is_good else (0, 0, 255)
                label = "Good" if obj.is_good else "Bad"
            else:
                color = (128, 128, 128)
                label = f"{oid}({obj.frame_count})"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return frame

    # ============================================================
    # 프레임 처리 API
    # ============================================================
    def process_frame(self, frame):
        h, w = frame.shape[:2]
        self.frame_width = w
        self.frame_height = h

        if self.roi is None:
            self._setup_roi(w, h)

        results = self.model(frame, conf=0.85, verbose=False)
        detections = []

        if len(results[0].boxes) > 0:
            boxes = results[0].boxes
            names = results[0].names

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                cls_name = names[cls_id]

                if cls_name in self.good_list or cls_name in self.bad_list:
                    detections.append(((x1, y1, x2, y2), cls_name, conf))

        out_list: List[bool] = []
        self._update_tracks(detections, out_list)

        disp = frame.copy()
        disp = self._draw_roi(disp)
        disp = self._draw_tracks(disp)

        return disp, out_list


# ============================================================
# 품질 검사 & 로그 (원하면 사용)
# ============================================================
class QualityInspector:
    def __init__(self, name="CAM"):
        self.name = name
        self.good = 0
        self.bad = 0

    def on_detection(self, r: DetectionResult):
        if r.is_defective:
            self.bad += 1
        else:
            self.good += 1


class DataLogger:
    def __init__(self, fname: str):
        self.fname = fname
        with open(self.fname, "w") as f:
            f.write("=== LOG START ===\n")

    def on_detection(self, r: DetectionResult):
        with open(self.fname, "a") as f:
            f.write(str(r.to_dict()) + "\n")

# ============================================================
# 실행부 — 카메라 0, 1 독립 처리 + 시작 신호/콜백 컨트롤러 예시
# ============================================================
def setup_camera(callbacks: list[Callable], shared_signals: dict):
    cam = CameraStream([0, 1])
    cam.start()

    vision0 = VisionAI(model_path, good_list=good_prod0, bad_list=bad_prod0)
    vision1 = VisionAI(model_path, good_list=good_prod1, bad_list=bad_prod1)

    inspector0 = QualityInspector("CAM0")
    inspector1 = QualityInspector("CAM1")

    logger0 = DataLogger("cam0_log.txt")
    logger1 = DataLogger("cam1_log.txt")

    # 시작 신호 + bool 콜백 컨트롤러 (카메라별 1개)
    signal0 = DetectionSignalController("CAM0")
    signal1 = DetectionSignalController("CAM1")
    shared_signals["CAM0"] = signal0
    shared_signals["CAM1"] = signal1

    # VisionAI 결과(DetectionResult)를 → bool로 변환해서 컨트롤러에 전달
    def bridge_cam0(res: DetectionResult):
        try:
            is_good = not res.is_defective
            signal0.handle_detection(is_good)
        except Exception as e:
            print(f"Bridge CAM0 error: {e}")

    def bridge_cam1(res: DetectionResult):
        try:
            is_good = not res.is_defective
            signal1.handle_detection(is_good)
        except Exception as e:
            print(f"Bridge CAM1 error: {e}")

    # VisionAI 콜백 등록 (순서: 인스펙터, 로거, 신호컨트롤러 브릿지)
    vision0.register_callback(inspector0.on_detection)
    vision0.register_callback(logger0.on_detection)
    vision0.register_callback(bridge_cam0)

    vision1.register_callback(inspector1.on_detection)
    vision1.register_callback(logger1.on_detection)
    vision1.register_callback(bridge_cam1)

    signal0.set_result_callback(callbacks[0])
    signal1.set_result_callback(callbacks[1])

    def vision_loop_cam():
        while True:
            f0 = cam.get_frame(0)
            f1 = cam.get_frame(1)

            if f0 is not None:
                out0, _ = vision0.process_frame(f0)
                cv2.imshow("CAM0", out0)

            if f1 is not None:
                out1, _ = vision1.process_frame(f1)
                cv2.imshow("CAM1", out1)

            if cv2.waitKey(1) == 27:
                break

        cam.stop()
        logger0.close()
        logger1.close()
        cv2.destroyAllWindows()
        
	  # Vision thread 시작
    t = threading.Thread(target=vision_loop_cam, daemon=True)
    t.start()

    shared_signals["RUNNING"] = True

# ============================================================
# 실행부 — 카메라 0, 1 독립 처리 + 시작 신호/콜백 컨트롤러 예시
# ============================================================
if __name__ == "__main__":
    cam = CameraStream([0, 1])
    cam.start()

    vision0 = VisionAI(model_path, good_list=good_prod0, bad_list=bad_prod0)
    vision1 = VisionAI(model_path, good_list=good_prod1, bad_list=bad_prod1)

    inspector0 = QualityInspector("CAM0")
    inspector1 = QualityInspector("CAM1")

    logger0 = DataLogger("cam0_log.txt")
    logger1 = DataLogger("cam1_log.txt")

    # 시작 신호 + bool 콜백 컨트롤러 (카메라별 1개)
    signal0 = DetectionSignalController("CAM0")
    signal1 = DetectionSignalController("CAM1")

    # VisionAI 결과(DetectionResult)를 → bool로 변환해서 컨트롤러에 전달
    def bridge_cam0(res: DetectionResult):
        is_good = not res.is_defective
        signal0.handle_detection(is_good)

    def bridge_cam1(res: DetectionResult):
        is_good = not res.is_defective
        signal1.handle_detection(is_good)

    # VisionAI 콜백 등록 (순서: 인스펙터, 로거, 신호컨트롤러 브릿지)
    vision0.register_callback(inspector0.on_detection)
    vision0.register_callback(logger0.on_detection)
    vision0.register_callback(bridge_cam0)

    vision1.register_callback(inspector1.on_detection)
    vision1.register_callback(logger1.on_detection)
    vision1.register_callback(bridge_cam1)

    # PLC와 실제 연결될 콜백 예시 (bool -> void)
    def plc_cam0_callback(is_good: bool):
        print(f"[PLC CAM0] WRITE: {'GOOD' if is_good else 'BAD'}")

    def plc_cam1_callback(is_good: bool):
        print(f"[PLC CAM1] WRITE: {'GOOD' if is_good else 'BAD'}")

    signal0.set_result_callback(plc_cam0_callback)
    signal1.set_result_callback(plc_cam1_callback)

    while True:
        f0 = cam.get_frame(0)
        f1 = cam.get_frame(1)

        if f0 is not None:
            out0, _ = vision0.process_frame(f0)
            cv2.imshow("CAM0", out0)

        if f1 is not None:
            out1, _ = vision1.process_frame(f1)
            cv2.imshow("CAM1", out1)

        key = cv2.waitKey(1)

        # 예시: 키보드 's' 입력 시 두 카메라 모두 다음 검출 1회만 허용
        # 실제 환경에서는 PLC 코드에서 signal0/1.request_start()를 호출하면 됨.
        if key == ord('s'):
            signal0.request_start()
            signal1.request_start()

        if key == 27:  # ESC
            break

    cam.stop()
    cv2.destroyAllWindows()
