
# TCP like reliable protocol

## Project Overview
This project implements a **TCP** like transport-layer protocol designed to provide reliable, in-order byte-stream delivery over the unreliable **UDP** transport. While UDP does not guarantee delivery, our protocol introduces reliability mechanisms including sequence numbers, cumulative acknowledgments, and retransmission timers to ensure data integrity between a sender and a receiver.

The project features a full implementation of the protocol as sender.py and receiver.py, as well as a simulated **Packet Loss and Corruption (PLC) module** to test the protocol's resilience under adverse network conditions, implemented in receiver.py

## Key Technical Features
*   **Reliable Data Transfer**: Implements a sliding window protocol that manages pipelined data transfer, ensuring all bytes are accounted for and delivered in the correct sequence.
*   **Connection Lifecycle Management**: 
    *   **Establishment**: A two-way handshake (SYN/ACK) to initialize sequence numbers.
    *   **Teardown**: A one-directional closure (FIN/ACK) to ensure all buffered data is received before termination.
*   **Error Detection**: Features a 16-bit checksum algorithm (one's complement sum) to detect bit-level corruption in both headers and payloads.
*   **Fast Retransmit**: Optimizes performance by detecting potential packet loss early; the sender retransmits the oldest unacknowledged segment immediately upon receiving three duplicate ACKs.
*   **Network Emulation (PLC)**: Includes a configurable module to simulate forward and reverse packet loss and bit-flip corruption, allowing for testing on a single host.

## Protocol Architecture

### Segment Structure
Every segment utilizes a fixed **6-byte header** to provide necessary control data.

| Field | Bits | Purpose |
| :--- | :--- | :--- |
| **Sequence Number** | 16 | Tracks byte-stream position or cumulative ACK progress. |
| **Reserved** | 13 | Bits reserved for further expansion. |
| **Control Bits** | 3 | Flags for segment types: **SYN**, **ACK**, or **FIN**. |
| **Checksum** | 16 | Validates the integrity of the entire datagram. |

### Flow Control & Error Recovery
*   **Sliding Window**: The sender uses a `max_win` constraint to manage how many bytes can be "in-flight" before requiring an acknowledgment.
*   **Selective Buffering**: The receiver identifies and buffers out-of-order segments, merging them into the main data stream once missing segments arrive to prevent redundant transmissions.
*   **Single Timer Logic**: The sender manages a single retransmission timer (`rto`) tied to the oldest unacknowledged segment.

## Usage and Execution

### Running the Simulation
Both components are designed to run on `localhost` (127.0.0.1) across different terminal instances.

1.  **Initialize the receiver**:
    ```bash
    python3 receiver.py <receiver_port> <sender_port> <output_file> <max_win>
    ```

2.  **Initialize the sender**:
    ```bash
    python3 sender.py <sender_port> <receiver_port> <file_to_send> <max_win> <rto> <flp> <rlp> <fcp> <rcp>
    ```

### Configuration Parameters
*   `max_win`: Maximum window size in bytes.
*   `rto`: Retransmission timeout duration in milliseconds.
*   `flp / rlp`: Probabilities (0.0 to 1.0) for packet loss in forward/reverse directions.
*   `fcp / rcp`: Probabilities (0.0 to 1.0) for packet corruption in forward/reverse directions.

## Logging and Metrics
Logs are generated to `sender_log.txt` and `receiver_log.txt`. These logs track every segment's direction, status (ok, drp, or cor), and sequence data. At the conclusion of a transfer, the system provides a summary of:
*   Total and original data/segments sent and received.
*   Counts of timeout and fast retransmissions.
*   Counts of PLC-triggered drops and corruptions.