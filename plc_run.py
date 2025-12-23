# plc_run.py
from plc_conn import PLC
import time

signal_sequence = [
    {'start': 'M1021','done': 'M2010'},
    {'start': 'M220', 'done': 'M2011'},
    {'start': 'M260', 'done': 'M2012'},
    {'start': 'M300', 'done': 'M2013'},
    {'start': 'M1028','done': 'M2014'}
]
EMERGENCY_STOP = 'X3'

def main(plc: PLC, trigger_callback):
    """
    Dobot의 스텝을 통제하기 위해 비동기적으로 PLC 신호를 읽기/쓰기하는 제어 로직
    
    :param trigger_callback: 스텝을 기록한 콜백 함수
    """
    print("✅ PLC 신호 감시 시작 (Ctrl+C로 종료)")
    
    try:
        while True:
            try:
                # 비상정지 감시
                if plc.read_bit(EMERGENCY_STOP):
                    trigger_callback(-1)
                    time.sleep(0.3)
                    continue

                # Step 신호 감시
                for idx, signal in enumerate(signal_sequence, 1):
                    if plc.read_bit(signal['start']):
                        print(f"▶ Step {idx} 시작 신호 수신 ({signal['start']})")
                        #PLC > dobot 신호 0.5초 딜레이
                        time.sleep(1.0)

                        trigger_callback(idx)
                        #dobot > PLC 신호 0.5초 딜레이
                        time.sleep(1.0)

                        plc.write_bit(signal['done'], True)
                        time.sleep(0.5)
                        plc.write_bit(signal['done'], False)
                        print(f"✅ Step {idx} 완료 신호 전송 ({signal['done']})")

                time.sleep(0.2)

            except Exception as e:
                print(f"⚠️ PLC 통신 중 오류 발생: {e}")
                time.sleep(1)  # 1초 후 재시도

    except KeyboardInterrupt:
        print("🛑 사용자 종료 요청 (Ctrl+C)")
    finally:
        plc.close()
        print("🔌 PLC 연결 종료")
