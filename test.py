# test_plc.py
from plc_conn import PLC

plc = PLC(ip='192.168.3.10', port=5010)

print("테스트 시작")
print("read_bit 함수:", hasattr(plc, 'read_bit'))
print("read_word 함수:", hasattr(plc, 'read_word'))

if hasattr(plc, 'read_bit'):
    print("M21 상태:", plc.read_bit('M21'))

plc.close()
