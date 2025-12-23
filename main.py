#main.py

import threading
import time
from detector import setup_camera
from plc_run import main as plc_main
from plc_conn import PLC
from dobot_motion import setup_dobot, move_to, suction, execute_queue
from point import A1, B1, C1, D1, E1, F1, G1, H1, I1
from point import A2, B2, C2, D2, E2, F2, G2
from point import A3, B3, C3, D3, E3, F3, G3, H3, I3, J3
import DobotDllType as dType

plc = None
# COM 정보만 저장 (연결은 필요할 때 수행)
dobot_com = {
    'dobot1': 'COM3',
    'dobot2': 'COM4'
}
shared_signals = {}

def dobot_step(step_index, _api_map=None):
    if not plc:
        return

    """Step별로 Dobot 연결/동작/해제 처리"""
    # Emergency Stop 처리
    if step_index == -1:
        print("⚠️ [비상정지] 두봇 즉시 정지")
        for com in dobot_com.values():
            try:
                api = setup_dobot(com)
                dType.SetQueuedCmdClear(api)
                dType.SetQueuedCmdStopExec(api)
                dType.DisconnectDobot(api)
            except Exception as e:
                print(f"[비상정지] {com} 처리 중 오류: {e}")
        return

    # Step에 따라 어떤 Dobot 사용
    target_com = (
        dobot_com['dobot1'] if step_index in [1, 2]
        else dobot_com['dobot2']
    )

    # Dobot 연결
    try:
        api = setup_dobot(target_com)
        print(f"\n▶ Step {step_index} 동작 시작 (사용 포트: {target_com})")
    except Exception as e:
        print(f"❌ Dobot 연결 실패 ({target_com}): {e}")
        return

    last_index = 0

    def move_and_wait(api, point):
        last_index = move_to(api, point)
        execute_queue(api, last_index)
        return last_index

    def suction_sync(api, enable=True):
        suction(api, enable)
        execute_queue(api, dType.GetQueuedCmdCurrentIndex(api)[0])
    
    try:
        if step_index == 1:
            plc.write_bit_in_real_time("M0", "1") # 웨이퍼 배출 ON
            plc.write_bit_in_real_time("M100", "1") # 두봇 STEP 1 ON
            move_and_wait(api, A1)
            move_and_wait(api, B1)
            move_and_wait(api, C1)
            plc.write_bit_in_real_time("M0", "0") # 웨이퍼 배출 ON
            suction_sync(api, True)
            move_and_wait(api, B1)
            move_and_wait(api, A1)
            move_and_wait(api, D1)
            move_and_wait(api, E1)
            suction_sync(api, False)
            move_and_wait(api, D1)
            move_and_wait(api, A1)
            plc.write_bit_in_real_time("M100", "0") # 두봇 STEP 1 OFF
            plc.write_bit_in_real_time("M101", "1") # 연마기 회전 ON
            plc.write_bit_in_real_time("M102", "1") # 연마기 실린더 하강 ON

        
        elif step_index == 2:
            plc.write_bit_in_real_time("M101", "0") # 연마기 회전 OFF
            plc.write_bit_in_real_time("M102", "0") # 연마기 실린더 OFF
            plc.write_bit_in_real_time("M103", "1") # 연마기 실린더 상승 ON
            plc.write_bit_in_real_time("M200", "1") # 두봇 STEP 2 ON
            shared_signals["CAM1"].request_start()          # 0번 카메라 양불량 감지 시작
            move_and_wait(api, A1)
            move_and_wait(api, D1)
            move_and_wait(api, E1)
            move_and_wait(api, F1)
            suction_sync(api, True)
            move_and_wait(api, E1)
            move_and_wait(api, G1)
            move_and_wait(api, H1)
            move_and_wait(api, I1)
            suction_sync(api, False)
            move_and_wait(api, H1)
            move_and_wait(api, G1)
            move_and_wait(api, D1)
            move_and_wait(api, A1)
            plc.write_bit_in_real_time("M103", "0") # 연마기 실린더 상승 OFF
            plc.write_bit_in_real_time("M200", "0") # 두봇 STEP 2 OFF
            plc.write_bit_in_real_time("M201", "1") # 컨베이어1 ON


        elif step_index == 3:
            plc.write_bit_in_real_time("M201", "0") # 컨베이어 OFF
            plc.write_bit_in_real_time("M300", "1") # 두봇 STEP 3 ON
            move_and_wait(api, A2)
            move_and_wait(api, B2)
            move_and_wait(api, C2)
            suction_sync(api, True)
            move_and_wait(api, B2)
            move_and_wait(api, A2)
            move_and_wait(api, D2)
            suction_sync(api, False)
            move_and_wait(api, A2)
            plc.write_bit_in_real_time("M300", "0") # 두봇 STEP 3 OFF
            plc.write_bit_in_real_time("M301", "1") # 분사기 회전 ON
            plc.write_bit_in_real_time("M302", "1") # 분사기 분무 ON

        elif step_index == 4:
            plc.write_bit_in_real_time("M203", "1") # 스토퍼 상승 ON
            plc.write_bit_in_real_time("M301", "0") # 분사기 회전 OFF
            plc.write_bit_in_real_time("M302", "0") # 분사기 분무 OFF
            plc.write_bit_in_real_time("M303", "1") # 분사기 원위치 ON
            plc.write_bit_in_real_time("M400", "1") # 두봇 STEP 4 ON
            shared_signals["CAM0"].request_start()          # 1번 카메라 양불량 감지 시작
            move_and_wait(api, A2)
            move_and_wait(api, D2)
            move_and_wait(api, E2)
            suction_sync(api, True)
            move_and_wait(api, D2)
            move_and_wait(api, A2)
            move_and_wait(api, F2)
            move_and_wait(api, G2)
            suction_sync(api, False)
            move_and_wait(api, F2)
            move_and_wait(api, A2)
            plc.write_bit_in_real_time("M203", "0") # 스토퍼 상승 OFF
            plc.write_bit_in_real_time("M303", "0") # 분사기 원위치 OFF
            plc.write_bit_in_real_time("M400", "0") # 두봇 STEP 4 ON
            plc.write_bit_in_real_time("M401", "1") # 컨베이어2 ON
            

        elif step_index == 5:
            plc.write_bit_in_real_time("M401", "0") # 컨베이어2 OFF
            plc.write_bit_in_real_time("M500", "1") # 두봇 STEP 5 ON
            move_and_wait(api, A3)
            time.sleep(2.0)
            move_and_wait(api, B3)
            move_and_wait(api, C3)
            move_and_wait(api, D3)
            move_and_wait(api, E3)
            move_and_wait(api, F3)
            suction_sync(api, True)
            move_and_wait(api, E3)
            move_and_wait(api, G3)
            move_and_wait(api, H3)
            move_and_wait(api, I3)
            move_and_wait(api, J3)
            suction_sync(api, False)
            move_and_wait(api, I3)
            move_and_wait(api, H3)
            move_and_wait(api, G3)
            move_and_wait(api, D3)
            move_and_wait(api, C3)
            move_and_wait(api, B3)
            move_and_wait(api, A3)
            plc.write_bit_in_real_time("M500", "0") # 두봇 STEP 5 OFF
    except Exception as e:
        print("❌ Dobot Step 작동 과정 중 오류 발생")
        print(e)

    # 큐 실행
    try:
        execute_queue(api, last_index)
    except Exception as e:
        print(f"❌ Step {step_index} 실행 중 오류: {e}")

    # Dobot 연결 해제
    try:
        dType.DisconnectDobot(api)
        print(f"✅ Step {step_index} 동작 완료 (COM {target_com} 연결 해제)\n")
    except Exception as e:
        print(f"❌ Dobot 연결 해제 오류: {e}")


# 프로그램 시작
if __name__ == "__main__":
    print("🔌 PLC 신호 감시 시작 (Ctrl+C로 종료)\n")

    plc = PLC(ip='192.168.3.10', port=5010)
		
    setup_camera(
        callbacks=[
            lambda r: plc.async_plc_write(idx=1, is_good_bad=r),            # 0번 카메라 양품 신호
            lambda r: plc.async_plc_write(idx=0, is_good_bad=r)             # 1번 카메라 양품 신호
        ],
        shared_signals=shared_signals
    )
    
    # 검사용 프로그램 완전 작동 시까지 대기
    while not shared_signals.get("RUNNING"):
        time.sleep(0.1)

    print("\n✅ Vision AI 연결 완료")

    try:
        plc_main(plc, dobot_step)  # dobot_step만 전달
    except KeyboardInterrupt:
        print("\n🛑 사용자 종료 요청 (Ctrl+C)")
    except Exception as e:
        print(f"❌ 프로그램 전체 오류 발생: {e}")
