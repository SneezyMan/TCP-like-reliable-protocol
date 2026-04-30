"""
    Python 3
    Usage: python3 receiver.py receiver_port sender_port txt_file_received max_win
"""
from socket import *
import sys, time, struct

MSS = 1000
FLAG_ACK, FLAG_SYN, FLAG_FIN = 0b100, 0b010, 0b001

t0 = None
receiver_log = open("receiver_log.txt", "w", buffering=1)

def now_ms() -> int:
	return (time.monotonic() - t0) * 1000.0

def u16(x: int) -> int:
	return x & 0xFFFF

def get_check_sum(buffer: bytes) -> int:
	if len(buffer) % 2 == 1:
		buffer += b'\x00'
	result = 0
	for i in range(0, len(buffer), 2):
		word = (buffer[i] << 8) + buffer[i + 1]
		result += word
		result = (result & 0xFFFF) + (result >> 16)
	return ~result & 0xFFFF

def build_ack(seq: int) -> bytes:
	header = struct.pack(">HHH", seq, FLAG_ACK, 0)
	check_sum = get_check_sum(header)
	segment = struct.pack(">HHH", seq, FLAG_ACK, check_sum)
	return segment

def parse_segment(datagram: bytes):
	header = struct.unpack(">HHH", datagram[:6])
	seq = header[0]
	flags = header[1]
	check_sum = header[2]
	payload = datagram[6:]
	if (get_check_sum(datagram[:4] + b'\x00\x00' + payload) == check_sum):
		corrupt = False
	else:
		corrupt = True
	return seq, flags, payload, corrupt

def log(direction, status, segType, seq, payload_len):
  receiver_log.write(f"{direction:5}\t{status:5}\t{now_ms():7.2f}\t{segType:4}\t{seq:7}\t{payload_len:5}\n")
 
def log_final():
  receiver_log.write("\n")
  receiver_log.write(f"{'Original data received:':35}{original_data_rcv}\n")
  receiver_log.write(f"{'Total data received:':35}{total_data_rcv}\n")
  receiver_log.write(f"{'Original segments received:':35}{original_segment_rcv}\n")
  receiver_log.write(f"{'Total segments received:':35}{total_segment_rcv}\n")
  receiver_log.write(f"{'Corrupted segments discarded:':35}{corrupt_segment_disc}\n")
  receiver_log.write(f"{'Duplicate segments received:':35}{dupl_segment_rcv}\n")
  receiver_log.write(f"{'Total acks sent:':35}{total_ack_sent}\n")
  receiver_log.write(f"{'Duplicate acks sent:':35}{dupl_ack_sent}\n")

receiver_port = int(sys.argv[1])
sender_port = int(sys.argv[2])
txt_file_received = (sys.argv[3])
max_win = int(sys.argv[4])

receiver_socket = socket(AF_INET, SOCK_DGRAM)
receiver_socket.bind(("127.0.0.1", receiver_port))
sender_address = ("127.0.0.1", sender_port)

original_data_rcv = 0
total_data_rcv = 0
original_segment_rcv = 0
total_segment_rcv = 0
corrupt_segment_disc = 0
dupl_segment_rcv = 0
total_ack_sent = 0
dupl_ack_sent = 0
recv_buffer = {}

# Connection establishment
expected = None
last_ack = None

while True:
  data, address = receiver_socket.recvfrom(2048)
  seq, flags, payload, corrupt = parse_segment(data)

  if t0 is None:
    t0 = time.monotonic()

  if corrupt:
    log("rcv", "cor", "SYN", seq, len(payload))
    corrupt_segment_disc += 1
    continue

  if flags & FLAG_SYN:
    log("rcv", "ok", "SYN", seq, len(payload))
    expected = u16(seq + 1)
    ackSeg = build_ack(expected)
    receiver_socket.sendto(ackSeg, sender_address)
    
    log("snd", "ok", "ACK", expected, 0)
    total_ack_sent += 1
    last_ack = expected
    break

  log("rcv", "cor", "SYN", seq, len(payload))
  corrupt_segment_disc += 1

# Data transfer and Connection closure
with open(txt_file_received, "wb") as file:
  while True:
    data, address = receiver_socket.recvfrom(2048)
    seq, flags, payload, corrupt = parse_segment(data)
    total_segment_rcv += 1

    if t0 is None:
      t0 = time.monotonic()

    # Handle stray SYNs during data phase
    if flags & FLAG_SYN:
      if corrupt:
        log("rcv", "cor", "SYN", seq, len(payload))
        corrupt_segment_disc += 1
        continue
      log("rcv", "ok", "SYN", seq, len(payload))
      ack = build_ack(expected)
      receiver_socket.sendto(ack, sender_address)
      log("snd", "ok", "ACK", expected, 0)
      total_ack_sent += 1
      continue

    # Handle FIN
    if flags & FLAG_FIN:
      if corrupt:
        log("rcv", "cor", "FIN", seq, 0)
        corrupt_segment_disc += 1
        continue

      log("rcv", "ok", "FIN", seq, 0)
      if seq == expected:
        expected = u16(expected + 1)

      fin_ack = build_ack(expected)
      receiver_socket.sendto(fin_ack, sender_address)
      log("snd", "ok", "ACK", expected, 0)
      total_ack_sent += 1

      # TIME_WAIT after receiving FIN
      end_time = time.monotonic() + 2.0
      receiver_socket.settimeout(0.2)
      while time.monotonic() < end_time:
        try:
          data, address = receiver_socket.recvfrom(2048)
        except timeout:
          continue
        seq2, flags2, payload2, corrupt2 = parse_segment(data)
        if (flags2 & FLAG_FIN) and not corrupt2:
          receiver_socket.sendto(fin_ack, sender_address)
          log("snd", "ok", "ACK", expected, 0)
          total_ack_sent += 1
          end_time = time.monotonic() + 2.0
      break

    # Corrupted DATA
    if corrupt:
      log("rcv", "cor", "DATA", seq, len(payload))
      corrupt_segment_disc += 1
      if expected is not None:
        ack = build_ack(expected)
        receiver_socket.sendto(ack, sender_address)
        log("snd", "dup", "ACK", expected, 0)
        total_ack_sent += 1
        dupl_ack_sent += 1
      continue

    # In-order DATA
    if seq == expected:
      log("rcv", "ok", "DATA", seq, len(payload))
      file.write(payload)
      original_data_rcv += len(payload)
      total_data_rcv += len(payload)
      original_segment_rcv += 1

      expected = u16(expected + len(payload))

      while True:
        buffered = recv_buffer.get(expected)
        if buffered is None:
          break

        log("rcv", "ok", "DATA", expected, len(buffered))
        file.write(buffered)
        original_data_rcv += len(buffered)
        total_data_rcv += len(buffered)
        original_segment_rcv += 1

        del recv_buffer[expected]
        expected = u16(expected + len(buffered))

      ack = build_ack(expected)
      receiver_socket.sendto(ack, sender_address)
      log("snd", "ok", "ACK", expected, len(payload))
      total_ack_sent += 1
      last_ack = expected
      continue

    # Out-of-order DATA
    if seq in recv_buffer:
      dupl_segment_rcv += 1
      log("rcv", "dup", "DATA", seq, len(payload))
    else:
      log("rcv", "ok", "DATA", seq, len(payload))
      recv_buffer[seq] = payload

    ack = build_ack(expected)
    receiver_socket.sendto(ack, sender_address)
    total_ack_sent += 1

    if last_ack == expected:
      dupl_ack_sent += 1
      log("snd", "dup", "ACK", expected, 0)
    else:
      log("snd", "ok", "ACK", expected, 0)

    last_ack = expected

log_final()
receiver_log.close()
receiver_socket.close()
