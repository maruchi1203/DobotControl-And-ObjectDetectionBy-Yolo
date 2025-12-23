import DobotDllType as dType

api = dType.load()
state = dType.ConnectDobot(api, "com4", 115200)[0]

if state == dType.DobotConnect.DobotConnect_NoError:

    # 현재 좌표 읽기
    pose = dType.GetPose(api)

    # pose는 [x, y, z, r] 형태로 반환
    print(f"현재 위치:")
    print(f"X: {pose[0]:.3f} mm")
    print(f"Y: {pose[1]:.3f} mm")
    print(f"Z: {pose[2]:.3f} mm")
    print(f"R: {pose[3]:.3f} deg")

    dType.DisconnectDobot(api)
else:
    print("Dobot 연결 실패")
