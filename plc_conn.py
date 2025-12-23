#plc_conn.py

import sys
import threading
import time
import pymcprotocol
import requests

class PLC:
    url = "http://127.0.0.1:8080/status/update" if len(sys.argv) > 1 else "http://127.0.0.1:8080/status/update"
    headers = {"x-api-key": "1111"}
    signal_for_OD_result = {
        "Waper1Good": "M2100",
        "Waper1Bad": "M2101",
        "Waper2Good": "M2102",
        "Waper2Bad": "M2103",
    }

    def __init__(self, ip='192.168.3.10', port=5010, retry=3, retry_interval=2):
        """
        Mitsubishi PLC 연결 클래스
        :param ip: PLC IP 주소
        :param port: PLC 통신 포트
        :param retry: 연결 재시도 횟수
        :param retry_interval: 재시도 간격 (초)
        """
        self.ip = ip
        self.port = port
        self.retry = retry
        self.retry_interval = retry_interval
        self.mc = pymcprotocol.Type3E()
        self.plc_lock = threading.Lock()
        self.connected = False
        self.connect()

    def connect(self):
        """PLC 연결 시도 (재시도 포함)"""
        for i in range(self.retry):
            try:
                self.mc.connect(self.ip, self.port)
                self.connected = True
                print(f"[✅ PLC 연결 성공] {self.ip}:{self.port}")
                return
            except Exception as e:
                print(f"[❌ PLC 연결 실패 {i+1}/{self.retry}] {e}")
                time.sleep(self.retry_interval)
        print("[⚠️ PLC 연결 불가 — 재시도 모두 실패]")
        self.connected = False

    def read_bit(self, device='M100', size=1):
        """비트 디바이스(M, X, Y 등) 읽기"""
        try:
            data = self.mc.batchread_bitunits(device, size)
            return data[0] if size == 1 else data
        except Exception as e:
            print(f"[⚠️ PLC 비트 읽기 오류] {e}")
            return None

    def write_bit(self, device='M100', value=True):
        """비트 디바이스(M, X, Y 등) 쓰기"""
        try:
            self.mc.batchwrite_bitunits(device, [int(value)])
            print(f"[PLC 비트 쓰기] {device} ← {value}")
        except Exception as e:
            print(f"[⚠️ PLC 비트 쓰기 오류] {e}")

    def write_bit_for_vision_callback(self, idx:int, is_good: bool):
        """
            2025.12.09 추가 로직\n
            Vision 검사에서 양불량 판정 시 해당 로직을 작동시켜
            PLC 메모리 디바이스에 쓰기를 수행함
            (메모리 디바이스 해제까지 0.5초 지연)\n

            0번 CAM\n
            M2100 : 양품 검출 / M2101 : 불량품 검출

            1번 CAM\n
            M2102 : 양품 검출 / M2103 : 불량품 검출

            :param is_good_bad: 양/불량 검출 신호
        """
        with self.plc_lock:
            try:
                print(f"[PLC Write] idx={idx}, is_good_bad={is_good}, thread={threading.current_thread().name}")
                if idx == 0:
                    if is_good:
                        device = self.signal_for_OD_result["Waper1Good"]
                    else:
                        self.write_bit_in_real_time("M401", "1") # 컨베이어 - 끝까지 가기 OFF
                        self.write_bit_in_real_time("M202", "1") # 컨베이어 - 스토퍼 히강 ON
                        device = self.signal_for_OD_result["Waper1Bad"]
                elif idx == 1:
                    device = self.signal_for_OD_result["Waper2Good"] if is_good else self.signal_for_OD_result["Waper2Bad"]
                else:
                    print(f"[❌ 오류] 잘못된 idx 값: {idx}")
                    return
                
                # PLC 쓰기 (ON)
                self.mc.batchwrite_bitunits(device, [1])
                print(f"[PLC] {device} = ON")

                # 3초 유지
                time.sleep(3.0)
                
                # PLC 쓰기 (OFF)
                self.mc.batchwrite_bitunits(device, [0])
                print(f"[PLC] {device} = OFF")
                self.write_bit_in_real_time("M401", "0") # 컨베이어 - 끝까지 가기 OFF
                if is_good:
                    self.write_bit_in_real_time("M202", "0") # 컨베이어 - 스토퍼 히강 OFF
                else:
                    self.write_bit_in_real_time("M600", "1") # 컨베이어 - 끝까지 가기 OFF
                    time.sleep(1.5)
                    self.write_bit_in_real_time("M600", "0") # 컨베이어 - 끝까지 가기 OFF

            except Exception as e:
                print(f"[⚠️ PLC 비트 쓰기 오류] {e}")

    def async_plc_write(self, idx:int, is_good_bad: bool):
        """
        2025.12.09 추가 로직\n
        write_bit_for_vision_callback을 비동기적으로 실행하여
        실시간 PLC 데이터 쓰기를 보장함
        
        :param is_good_bad: 양/불량 검출 신호
        """
        threading.Thread(
            target=lambda: self.write_bit_for_vision_callback(idx, is_good_bad),
            daemon=True,
            name=f"PLC-CAM{idx}"  # 디버깅용 스레드 이름
        ).start()

    def read_word(self, device='D100', size=1):
        """워드 디바이스(D 영역) 읽기"""
        try:
            data = self.mc.batchread_wordunits(device, size)
            return data[0] if size == 1 else data
        except Exception as e:
            print(f"[⚠️ PLC 워드 읽기 오류] {e}")
            return None

    def write_word(self, device='D100', value=0):
        """워드 디바이스(D 영역) 쓰기"""
        try:
            self.mc.batchwrite_wordunits(device, [int(value)])
            print(f"[PLC 워드 쓰기] {device} ← {value}")
        except Exception as e:
            print(f"[⚠️ PLC 워드 쓰기 오류] {e}")

    def is_connected(self):
        """PLC 연결 상태 확인"""
        return self.connected

    def close(self):
        """PLC 연결 해제"""
        try:
            self.mc.close()
            print("[🔌 PLC 연결 해제 완료]")
        except Exception as e:
            print(f"[⚠️ 연결 해제 중 오류] {e}")
        self.connected = False

    def write_bit_in_real_time(self, tag: str, val: str):
        if not self.connected:
            return

        payload = {
            "plc_id" : "PLC1",
            "tag" : tag,
            "val" : val
        }

        try:
            requests.post(
                    self.url,
                    json=payload,
                    headers=self.headers,
                    timeout=1
                ) 
        except Exception as e:
            print(f"[⚠️ 상태 전송 실패] {e}")

    def _parse_device(self, addr):
        dev = addr[0]
        body = addr[1:]
        if dev in ("X", "Y"):
            return dev, int(body, 16)
        return dev, int(body)

    def _word_base(self, bit_addr):
        return bit_addr - (bit_addr % 16)

    def _get_bit(self, word, idx):
        return (word >> idx) & 1
    
    def start_monitoring(self, interval=0.5):
        def loop():
            while self.connected:
                self.read_bit_in_real_time()
                time.sleep(interval)

        threading.Thread(
            target=loop,
            daemon=True,
            name="PLC-Monitor"
        ).start()


# ---------------- 테스트 실행 ---------------- # plc_conn 단독 실행 용 코드로 본 코드에 영향x
if __name__ == "__main__":
    plc = PLC(ip="192.168.3.10", port=5010)
    if plc.is_connected():
        print("PLC와 통신이 가능한 상태입니다 ✅")
        plc.read_bit("M0")
        input("Enter 시 종료 실행")
    else:
        print("PLC 연결 실패 ❌, IP나 포트 설정을 확인하세요.")
    plc.close()

'''
# --------- PLC 신호로 연결 및 종료 ------------ #
if __name__ == "__main__":
    plc = PLC(ip="192.168.3.10", port=5010)
    if plc.is_connected():
        # 예: D 레지스터 100번 읽기
        value = plc.mc.batchread_words("D100", 1)
        print("D100 값:", value)

        # 예: D 레지스터 101번 쓰기
        plc.mc.batchwrite_words("D101", [123])
        print("D101에 123 기록 완료")
    plc.close()
'''