#해당 원인 발견
# 해당 원인은 포트 2개를 동시연결하기에 신호의 충돌로 com3으로 보내야하는지 com4로 보내야하는지 못찾음
# com3를 우선 연결 후 step3를 시작 할 때 com3를 끊고 com4를 연결하는 식으로 진행


from plc_run import PLC  # 기존 plc_conn 내용 사용
from dobot_motion import setup_dobot, move_to, execute_queue, suction
from point import A1, B1, C1, D1, E1, F1, G1, H1, I1
import DobotDllType as dType
import threading
import time
from collections import deque

# ---------------- Dobot 연결 ----------------
api1 = setup_dobot("COM3")  # Step1,2용
api2 = None                  # Step3,4용 (나중 연결)

api_map = {'dobot1': api1}  # 현재 COM3만 활성화

# ---------------- Step → Dobot 매핑 ----------------
step_robot_map = {
    1: 'dobot1',
    2: 'dobot1',
    3: 'dobot2',  # 나중 연결
    4: 'dobot2'
}

# ---------------- Step 우선순위 ----------------
step_priority = {
    'dobot1': [2, 1],
    'dobot2': [4, 3]
}

# ---------------- Step 큐 ----------------
robot_queues = {
    'dobot1': deque(),
    'dobot2': deque()
}

running_steps = set()
lock = threading.Lock()

# ---------------- Dobot 동작 ----------------
def move_and_wait(api, point):
    last_index = move_to(api, point)
    execute_queue(api, last_index)
    return last_index

def dobot_step(step_index, api):
    """Step에 따라 Dobot 실행"""
    if step_index == -1:  # 비상정지
        print("⚠️ [E-STOP] Dobot 정지")
        dType.SetQueuedCmdStopExec(api)
        return

    print(f"▶ Step {step_index} 시작 (사용 Dobot: {api})")
    last_index = 0

    # Step1,2 → COM3 Dobot
    if step_index == 1:
        move_and_wait(api, A1)
        move_and_wait(api, B1)
        move_and_wait(api, C1)
        suction(api, True)
        move_and_wait(api, A1)
        suction(api, False)
        
    elif step_index == 2:
        move_and_wait(api, A1)
        move_and_wait(api, D1)
        move_and_wait(api, E1)
        move_and_wait(api, F1)
        suction(api, True)
        move_and_wait(api, G1)
        move_and_wait(api, H1)
        move_and_wait(api, I1)
        suction(api, False)
        move_and_wait(api, H1)
        move_and_wait(api, G1)
        move_and_wait(api, A1)

    # Step3,4 → COM4 Dobot (나중 연결)
    elif step_index in [3,4]:
        global api2
        if api2 is None:
            print("COM4 Dobot 연결 중...")
            api2 = setup_dobot("COM4")
            api_map['dobot2'] = api2
        # 실제 Step3,4 동작 함수는 여기에 추가 가능
        print(f"Step {step_index} 준비 완료 (COM4 Dobot)")

    print(f"✅ Step {step_index} 완료")

# ---------------- 큐 스케줄러 ----------------
def schedule_step(step_index, robot_name, api, trigger_callback):
    with lock:
        robot_queues[robot_name].append(step_index)
    process_queue(robot_name, api, trigger_callback)

def process_queue(robot_name, api, trigger_callback):
    with lock:
        if robot_name in running_steps:
            return
        queue = robot_queues[robot_name]
        next_step = None
        for step in step_priority[robot_name]:
            if step in queue:
                next_step = step
                queue.remove(step)
                break
        if next_step is None:
            return
        running_steps.add(robot_name)

    def run_step():
        try:
            trigger_callback(next_step, api)
        finally:
            with lock:
                running_steps.remove(robot_name)
            process_queue(robot_name, api, trigger_callback)

    threading.Thread(target=run_step).start()

# ---------------- PLC 감시 ----------------
def main(trigger_callback, api_map):
    plc = PLC(ip='192.168.3.10', port=5010)
    print("✅ PLC 신호 감시 시작 (Ctrl+C로 종료)")

    signal_sequence = [
        {'start': 'M1021', 'done': 'M2010'},  # Step1
        {'start': 'M220',  'done': 'M2011'},  # Step2
        {'start': 'M1025', 'done': 'M2012'},  # Step3
        {'start': 'M300',  'done': 'M2013'}   # Step4
    ]

    step_robot_name_map = {1:'dobot1', 2:'dobot1', 3:'dobot2', 4:'dobot2'}
    EMERGENCY_STOP = 'X3'

    try:
        while True:
            if plc.read_bit(EMERGENCY_STOP):
                print("⚠️ [E-STOP] 모든 Dobot 정지")
                for api in api_map.values():
                    trigger_callback(-1, api)
                time.sleep(0.3)
                continue

            for idx, signal in enumerate(signal_sequence, 1):
                if plc.read_bit(signal['start']):
                    robot_name = step_robot_name_map[idx]
                    api = api_map.get(robot_name)
                    if api is None:
                        print(f"⚠️ {robot_name} Dobot 미연결")
                        continue
                    schedule_step(idx, robot_name, api, trigger_callback)

                    # 완료 신호
                    time.sleep(1.0)
                    plc.write_bit(signal['done'], True)
                    time.sleep(0.5)
                    plc.write_bit(signal['done'], False)
                    print(f"✅ Step {idx} 완료 신호 전송 ({signal['done']})")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("🛑 사용자 종료 요청 (Ctrl+C)")
    finally:
        plc.close()
        for api in api_map.values():
            dType.DisconnectDobot(api)
        print("🔌 모든 Dobot 연결 종료")

# ---------------- 실행 ----------------
if __name__ == "__main__":
    main(dobot_step, api_map)
