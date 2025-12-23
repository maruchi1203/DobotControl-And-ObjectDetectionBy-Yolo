import time
import DobotDllType as dType
from pymcprotocol import Type3E

# ----------------------
# Dobot 연결
# ----------------------
CON_STR = {
    dType.DobotConnect.DobotConnect_NoError:  "DobotConnect_NoError",
    dType.DobotConnect.DobotConnect_NotFound: "DobotConnect_NotFound",
    dType.DobotConnect.DobotConnect_Occupied: "DobotConnect_Occupied"
}

api = dType.load()
state = dType.ConnectDobot(api, "", 115200)[0]
print("Connect status:", CON_STR[state])



# 큐 초기화
dType.SetQueuedCmdClear(api)
print("Dobot Clean completed")
# ----------------------
# 홈 좌표 설정
dType.SetHOMEParams(api, 200, 200, 200, 200, isQueued=1)

# Joint 속도/가속도 (각 관절)
dType.SetPTPJointParams(api, 50, 50, 50, 50, 50, 50, 50, 50, isQueued=1)
# XYZ 속도/가속도
dType.SetPTPCommonParams(api, 100, 100, isQueued=1)

# ----------------------
# PLC 연결
# ----------------------
plc = Type3E()
plc.connect("192.168.7.20", 5010)
print("PLC connected")

     
# ----------------------
# Dobot 이동 함수
# ----------------------
def move_dobot():
    print("Dobot moving")
    
    # 포인트 1
    dType.SetPTPCmd(api, dType.PTPMode.PTPMOVJXYZMode, 162, -63, 42, -21, isQueued=1)

    # 큐 실행
    dType.SetQueuedCmdStartExec(api)
    time.sleep(5)  # 단순히 5초 기다림
    print("Dobot task completed")



# ----------------------
# 상태 플래그
# ----------------------
dobot_busy = False

# ----------------------
# 메인 루프
# ----------------------
while True:
    x0_status = plc.batchread_bitunits("X0", 1)[0]

    if x0_status == 1 and not dobot_busy:
        print("X0 ON detected, turning M100 ON")
        plc.batchwrite_bitunits("M100", [1])
        dobot_busy = True

        move_dobot()

        print("Sending M101 ON to PLC")
        plc.batchwrite_bitunits("M101", [1])

        # M100 OFF 처리
        plc.batchwrite_bitunits("M100", [0])
        dobot_busy = False

    time.sleep(0.1)
