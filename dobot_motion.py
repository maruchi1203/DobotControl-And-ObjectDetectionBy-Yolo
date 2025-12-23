# dobot_motion.py
import DobotDllType as dType
from point import DOBOT1_PARAMS, DOBOT2_PARAMS
"""두봇 연결"""
def setup_dobot(com_port):
    api = dType.load()

    # COM 포트 지정하여 연결
    state = dType.ConnectDobot(api, com_port, 115200)[0]

    con_str = {
        dType.DobotConnect.DobotConnect_NoError:  "DobotConnect_NoError",
        dType.DobotConnect.DobotConnect_NotFound: "DobotConnect_NotFound",
        dType.DobotConnect.DobotConnect_Occupied: "DobotConnect_Occupied"
    }
    print(f"Connect status ({com_port}):", con_str[state])

    if state != dType.DobotConnect.DobotConnect_NoError:
        raise Exception(f"Dobot({com_port}) connection failed")

    # Dobot1 / Dobot2 구분
    if com_port == "COM3":
        params = DOBOT1_PARAMS
    elif com_port == "COM4":
        params = DOBOT2_PARAMS
    else:
        raise Exception(f"Unknown Dobot COM port: {com_port}")

    # 초기 세팅 적용
    dType.SetQueuedCmdClear(api)
    dType.SetHOMEParams(api, *params["HOME"], isQueued=1)
    dType.SetPTPJointParams(api, *params["PTP_JOINT"], isQueued=1)
    dType.SetPTPCommonParams(api, *params["PTP_COMMON"], isQueued=1)


    return api


"""PTP 이동 명령"""
def move_to(api, point):
    x, y, z, r = point
    return dType.SetPTPCmd(api, dType.PTPMode.PTPMOVLXYZMode, x, y, z, r, isQueued=1)[0]


"""흡착 제어"""
def suction(api, enable=True):
    dType.SetEndEffectorSuctionCup(api, 1, int(enable), isQueued=1)


"""명령 큐 실행 및 완료 대기"""
def execute_queue(api, last_index):
    dType.SetQueuedCmdStartExec(api)

    while last_index > dType.GetQueuedCmdCurrentIndex(api)[0]:
        dType.dSleep(100)

    # 큐 실행 정지
    dType.SetQueuedCmdStopExec(api)
