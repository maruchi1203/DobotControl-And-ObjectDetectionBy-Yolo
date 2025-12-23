# capture.py
# ------------------------------------------------------------
import cv2

capture = cv2.VideoCapture(1)
capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

idx = 0

while cv2.waitKey(1) != 27:
    ret, frame = capture.read()
    if cv2.waitKey(1) == 99:
        cv2.imwrite("./TestImage/Image" + str(idx) + ".jpg", frame)
        idx += 1
    cv2.imshow("VideoFrame", frame)
    
capture.release()
cv2.destroyAllWindows()