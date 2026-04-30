"""
    Python 3
    Usage: python3 sender.py sender_port receiver_port text_file_to_send max_win rto flp rlp fcp rcp
"""
import sys
from socket import *
import struct, time, random

MSS = 1000
FLAG_ACK, FLAG_SYN, FLAG_FIN = 0b100, 0b010, 0b001

t0 = None
sender_log = open("sender_log.txt", "w", buffering=1)

sender_port = int(sys.argv[1])
receiver_port = int(sys.argv[2])
text_file_to_send = sys.argv[3]
max_win = int(sys.argv[4])
rto = int(sys.argv[5])
flp = float(sys.argv[6])
rlp = float(sys.argv[7])
fcp = float(sys.argv[8])
rcp = float(sys.argv[9])

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

def build_segment(seq: int, flags: int, payload: bytes) -> bytes:
  header = struct.pack(">HHH", seq, flags, 0)
  check_sum = get_check_sum(header + payload)
  segment = struct.pack(">HHH", seq, flags, check_sum) + payload
  return segment

def parse_segment(datagram: bytes):
  header = struct.unpack(">HHH", datagram[:6])
  seq = header[0] & 0xFFFF
  flags = header[1] & 0xFFFF
  check_sum = header[2]
  payload = datagram[6:]

  if (get_check_sum(datagram[:4] + b'\x00\x00' + payload) == check_sum):
    corrupt = False
  else:
    corrupt = True
  return seq, flags, payload, corrupt

def log(direction, status, seg_type, seq, payload_len):
  sender_log.write(f"{direction:5}\t{status:5}\t{now_ms():7.2f}\t{seg_type:4}\t{seq:7}\t{payload_len:5}\n")
  
def log_final():
  sender_log.write("\n")
  sender_log.write(f"{'Original data sent:':35}{original_data_sent}\n")
  sender_log.write(f"{'Total data sent:':35}{total_data_sent}\n")
  sender_log.write(f"{'Original segments sent:':35}{original_segment_sent}\n")
  sender_log.write(f"{'Total segments sent:':35}{total_segment_sent}\n")
  sender_log.write(f"{'Timeout retransmissions:':35}{timeout_retransmits}\n")
  sender_log.write(f"{'Fast retransmissions:':35}{fast_retransmits}\n")
  sender_log.write(f"{'Duplicate acks received:':35}{duplicate_acks_recv}\n")
  sender_log.write(f"{'Corrupt acks discarded:':35}{corrupt_acks_disc}\n")
  sender_log.write(f"{'PLC forward segments dropped:':35}{plc_fwd_segment_dropped}\n")
  sender_log.write(f"{'PLC forward segments corrupted:':35}{plc_fwd_segment_corrupted}\n")
  sender_log.write(f"{'PLC reverse segments dropped:':35}{plc_rcv_segment_dropped}\n")
  sender_log.write(f"{'PLC reverse segments corrupted:':35}{plc_rcv_segment_dropped}\n")
  
def plc_send(segment: bytes):
  global plc_fwd_segment_dropped
  global plc_fwd_segment_corrupted
  if random.random() < flp:
    plc_fwd_segment_dropped += 1
    return "drp", segment
  if random.random() < fcp and len(segment) > 4:
    b = bytearray(segment)
    i = random.randrange(4, len(b))
    b[i] ^= 1 << random.randrange(8)
    plc_fwd_segment_corrupted += 1
    return "cor", bytes(b)
  return "ok", segment

def plc_receive(datagram: bytes):
  global plc_rcv_segment_dropped
  global plc_rcv_segment_dropped
  if random.random() < rlp:
    b = bytearray(datagram)
    plc_rcv_segment_dropped += 1
    return "drp", datagram
  if random.random() < rcp and len(datagram) > 4:
    b = bytearray(datagram)
    i = random.randrange(4, len(b))
    b[i] ^= 1 << random.randrange(8)
    plc_rcv_segment_dropped += 1
    return "cor", bytes(b)
  return "ok", datagram

def bytes_in_flight(base: int, next_seq: int) -> int:
  return u16(next_seq - base)

sender_socket = socket(AF_INET, SOCK_DGRAM)
sender_socket.bind(('127.0.0.1', sender_port))
receiver_address = ('127.0.0.1', receiver_port)
sender_socket.settimeout(rto/1000)

original_data_sent = 0
total_data_sent = 0
original_segment_sent = 0
total_segment_sent = 0
timeout_retransmits = 0
fast_retransmits = 0
duplicate_acks_recv = 0
corrupt_acks_disc = 0

plc_fwd_segment_dropped = 0
plc_fwd_segment_corrupted = 0
plc_rcv_segment_dropped = 0
plc_rcv_segment_dropped = 0

# Connection establishment
random.seed()
ISN = random.randint(0, 2**16 - 1)
syn = build_segment(ISN, FLAG_SYN, b'')
t0 = time.monotonic()
original_segment_sent += 1
ack_seen = {}
last_ack = None

status, output = plc_send(syn)
log("snd", status, "SYN", ISN, 0)
total_segment_sent += 1

if status != "drp":
  sender_socket.sendto(output, receiver_address)
send_time = now_ms()

while True:
  elapsed = now_ms() - send_time
  remaining = rto - elapsed
  
  if remaining <= 0:
    timeout_retransmits += 1
    
    status, output = plc_send(syn)
    log("snd", status, "SYN", ISN, 0)
    total_segment_sent += 1
    if status != "drp":
      sender_socket.sendto(output, receiver_address)
    
    send_time = now_ms()
    continue
  
  sender_socket.settimeout(remaining / 1000.0)
  try:
    data, address = sender_socket.recvfrom(2048)
  except timeout:
    continue

  status, output = plc_receive(data)
  ack_seq, flags, payload, corrupt = parse_segment(output)
  
  if status == "drp":
    log("rcv", "drp", "ACK", ack_seq, 0)
    continue

  if corrupt or status == "cor":
    log("rcv", "cor", "ACK", ack_seq, 0)
    corrupt_acks_disc += 1
    continue

  ack_seen[ack_seq] = ack_seen.get(ack_seq, 0) + 1
  syn_ack = u16(ISN + 1)
  
  log("rcv", "ok", "ACK", ack_seq, 0)
  if ack_seq == syn_ack:
    if ack_seq == last_ack:
      duplicate_acks_recv += 1
    last_ack = ack_seq
    break
  else:
    if ack_seq == last_ack:
      duplicate_acks_recv += 1
    continue

# Data transfer
with open(text_file_to_send, 'rb') as file:
  base = u16(ISN + 1)
  next_seq = base
  send_window = []
  file_finished = False
  send_time = None
  dup_ack_count = 0
  last_ack = None
  
  while not (file_finished and not send_window):
    while not file_finished and bytes_in_flight(base, next_seq) < max_win:
      chunk = file.read(MSS)
      if not chunk:
        file_finished = True
        break
      
      seg_seq = next_seq
      data_segment = build_segment(seg_seq, 0, chunk)
      original_data_sent += len(chunk)
      original_segment_sent += 1
      
      status, output = plc_send(data_segment)
      log("snd", status, "DATA", seg_seq, len(chunk))
      total_data_sent += len(chunk)
      total_segment_sent += 1
      
      if status != "drp":
        sender_socket.sendto(output, receiver_address)
        
      send_window.append({
				"seq": seg_seq,
				"len": len(chunk),
				"seg": data_segment,
			})
      
      if send_time == None and status != "drp":
        send_time = now_ms()
      next_seq = u16(next_seq + len(chunk))
      
    if not send_window:
      break
    
    if send_time == None:
      send_time = now_ms()
      
    elapsed = now_ms() - send_time
    remaining = rto - elapsed
    
    if remaining <= 0:
      oldest = send_window[0]
      timeout_retransmits += 1
      
      status, output = plc_send(oldest["seg"])
      log("snd", status, "DATA", oldest["seq"], oldest["len"])
      total_data_sent += oldest["len"]
      total_segment_sent += 1
      
      if status != "drp":
        sender_socket.sendto(output, receiver_address)
      send_time = now_ms()
      dup_ack_count = 0
      continue
    
    sender_socket.settimeout(remaining / 1000)
    try:
      data, address = sender_socket.recvfrom(2048)
    except timeout:
      continue

    status, output = plc_receive(data)
    ack_seq, flags, payload, corrupt = parse_segment(output)
  
    if status == "drp":
      log("rcv", "drp", "ACK", ack_seq, 0)
      continue
    
    if corrupt or status == "cor":
      corrupt_acks_disc += 1
      log("rcv", "cor", "ACK", ack_seq, 0)
      continue
    
    ack_seen[ack_seq] = ack_seen.get(ack_seq, 0) + 1
    log("rcv", "ok", "ACK", ack_seq, 0)
    inflight = bytes_in_flight(base, next_seq)
    bytes_acked = u16(ack_seq - base)
    
    if inflight > 0 and 0 < bytes_acked <= inflight:
      base = ack_seq
      dup_ack_count = 0
      remaining_bytes = bytes_acked
      
      while remaining_bytes > 0 and send_window:
        seg = send_window[0]
        
        if remaining_bytes >= seg["len"]:
          remaining_bytes -= seg["len"]
          send_window.pop(0)
        else:
          break
        
      if send_window:
        send_time = now_ms()
      else:
        send_time = None
      last_ack = ack_seq
    
    else:
      if ack_seq == last_ack:
        duplicate_acks_recv += 1
        dup_ack_count += 1
      else:
        dup_ack_count = 1
      last_ack = ack_seq
      
      if dup_ack_count >= 3 and send_window:
        oldest = send_window[0]
        fast_retransmits += 1
        
        status, output = plc_send(oldest["seg"])
        log("snd", status, "DATA", oldest["seq"], oldest["len"])
        total_data_sent += oldest["len"]
        total_segment_sent += 1
        
        if status != "drp":
          sender_socket.sendto(output, receiver_address)
        send_time = now_ms()
        dup_ack_count = 0

# Connection closure
fin = build_segment(next_seq, FLAG_FIN, b'')
original_segment_sent += 1
total_segment_sent += 1
status, output = plc_send(fin)
log("snd", status, "FIN", next_seq, 0)

if status != "drp":
  sender_socket.sendto(output, receiver_address)
send_time = now_ms()

while True:
  elapsed = now_ms() - send_time
  remaining = rto - elapsed
  
  if remaining <= 0:
    timeout_retransmits += 1
    
    status, output = plc_send(fin)
    log("snd", status, "FIN", u16(next_seq), 0)
    total_segment_sent += 1
    
    if status != "drp":
      sender_socket.sendto(output, receiver_address)
    send_time = now_ms()
    continue

  sender_socket.settimeout(remaining / 1000.0)
  try:
    data, address = sender_socket.recvfrom(2048)
  except timeout:
    continue

  status, output = plc_receive(data)
  ack_seq, flags, payload, corrupt = parse_segment(output)
  
  if status == "drp":
    log("rcv", "drp", "ACK", ack_seq, 0)
    continue

  if corrupt or status == "cor":
    corrupt_acks_disc += 1
    log("rcv", "cor", "ACK", ack_seq, 0)
    continue

  ack_seen[ack_seq] = ack_seen.get(ack_seq, 0) + 1
  final_ack = u16(next_seq + 1)

  log("rcv", "ok", "ACK", ack_seq, 0)
  if ack_seq == final_ack:
    if last_ack == ack_seq:
      duplicate_acks_recv += 1
    last_ack = ack_seq
    break
  else:
    if last_ack == ack_seq:
      duplicate_acks_recv += 1
    continue

log_final()
sender_log.close()
sender_socket.close()