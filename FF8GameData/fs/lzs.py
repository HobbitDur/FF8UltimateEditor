import time


class Lzs:
    """/!\\ Only decode have been tested"""
    N = 4096
    F = 18
    THRESHOLD = 2
    NIL = N

    def __init__(self):
        self.buffer = bytearray(Lzs.N + Lzs.F)
        self.MatchPos = 0
        self.MatchLen = 0
        self.Lson = [Lzs.NIL] * (Lzs.N + 1)
        self.Rson = [Lzs.NIL] * (Lzs.N + 257)
        self.Dad = [Lzs.NIL] * (Lzs.N + 1)

    def init_tree(self):
        for i in range(Lzs.N + 1, Lzs.N + 257):
            self.Rson[i] = Lzs.NIL
        for i in range(Lzs.N):
            self.Dad[i] = Lzs.NIL

    def insert_node(self, r):
        cmp = 1
        p = Lzs.N + 1 + self.buffer[r]
        self.Rson[r] = self.Lson[r] = Lzs.NIL
        self.MatchLen = 0
        while True:
            if cmp >= 0:
                if self.Rson[p] != Lzs.NIL:
                    p = self.Rson[p]
                else:
                    self.Rson[p] = r
                    self.Dad[r] = p
                    return
            else:
                if self.Lson[p] != Lzs.NIL:
                    p = self.Lson[p]
                else:
                    self.Lson[p] = r
                    self.Dad[r] = p
                    return
            for i in range(1, Lzs.F):
                cmp = self.buffer[r + i] - self.buffer[p + i]
                if cmp != 0:
                    break
            if i > self.MatchLen:
                self.MatchPos = p
                self.MatchLen = i
                if self.MatchLen >= Lzs.F:
                    break
        self.Dad[r] = self.Dad[p]
        self.Lson[r] = self.Lson[p]
        self.Rson[r] = self.Rson[p]
        self.Dad[self.Lson[p]] = r
        self.Dad[self.Rson[p]] = r
        if self.Rson[self.Dad[p]] == p:
            self.Rson[self.Dad[p]] = r
        else:
            self.Lson[self.Dad[p]] = r
        self.Dad[p] = Lzs.NIL

    def delete_node(self, p):
        if self.Dad[p] == Lzs.NIL:
            return
        if self.Rson[p] == Lzs.NIL:
            q = self.Lson[p]
        elif self.Lson[p] == Lzs.NIL:
            q = self.Rson[p]
        else:
            q = self.Lson[p]
            if self.Rson[q] != Lzs.NIL:
                while self.Rson[q] != Lzs.NIL:
                    q = self.Rson[q]
                self.Rson[self.Dad[q]] = self.Lson[q]
                self.Dad[self.Lson[q]] = self.Dad[q]
                self.Lson[q] = self.Lson[p]
                self.Dad[self.Lson[p]] = q
            self.Rson[q] = self.Rson[p]
            self.Dad[self.Rson[p]] = q
        self.Dad[q] = self.Dad[p]
        if self.Rson[self.Dad[p]] == p:
            self.Rson[self.Dad[p]] = q
        else:
            self.Lson[self.Dad[p]] = q
        self.Dad[p] = Lzs.NIL

    def encode(self, input_bytes: bytearray) -> bytearray:
        output_bytes = bytearray()
        self.init_tree()
        code_buf = bytearray(17)
        code_buf[0] = 0
        code_buf_ptr = mask = 1
        s = 0
        r = Lzs.N - Lzs.F
        len_input = len(input_bytes)
        input_pos = 0

        for i in range(s, r):
            self.buffer[i] = 0

        len_bytes = 0
        for len_bytes in range(Lzs.F):
            if input_pos < len_input:
                self.buffer[r + len_bytes] = input_bytes[input_pos]
                input_pos += 1
            else:
                break
        if len_bytes == 0:
            return bytearray()

        for i in range(1, Lzs.F + 1):
            self.insert_node(r - i)
        self.insert_node(r)

        while len_bytes > 0:
            if self.MatchLen > len_bytes:
                self.MatchLen = len_bytes
            if self.MatchLen <= Lzs.THRESHOLD:
                self.MatchLen = 1
                code_buf[0] |= mask
                code_buf[code_buf_ptr] = self.buffer[r]
                code_buf_ptr += 1
            else:
                code_buf[code_buf_ptr] = self.MatchPos & 0xFF
                code_buf_ptr += 1
                code_buf[code_buf_ptr] = ((self.MatchPos >> 4) & 0xF0) | (self.MatchLen - (Lzs.THRESHOLD + 1))
                code_buf_ptr += 1

            if (mask := mask << 1) == 0x100:
                output_bytes.extend(code_buf[:code_buf_ptr])
                code_buf[0] = 0
                code_buf_ptr = 1
                mask = 1

            last_match_length = self.MatchLen
            for i in range(last_match_length):
                if input_pos < len_input:
                    self.delete_node(s)
                    self.buffer[s] = input_bytes[input_pos]
                    input_pos += 1
                    if s < Lzs.F - 1:
                        self.buffer[s + Lzs.N] = input_bytes[input_pos - 1]
                    s = (s + 1) & (Lzs.N - 1)
                    r = (r + 1) & (Lzs.N - 1)
                    self.insert_node(r)
                else:
                    break

            len_bytes -= last_match_length

        if code_buf_ptr > 1:
            output_bytes.extend(code_buf[:code_buf_ptr])

        return output_bytes

    def decode(self, input_bytes: bytes):
        flags = 0
        input_pos = 0
        r = Lzs.N - Lzs.F
        buffer_size = Lzs.N - 1
        buffer = self.buffer  # Cache buffer for faster access
        input_len = len(input_bytes)  # Cache length of input_bytes

        def get_byte():
            """Fetch a byte from the input if available, otherwise return None."""
            nonlocal input_pos
            if input_pos < input_len:
                byte = input_bytes[input_pos]
                input_pos += 1
                return byte
            return None

        while input_pos < input_len:
            # Refill flags when exhausted (process batch if possible)
            if flags & 0x100 == 0:
                next_byte = get_byte()
                if next_byte is None:
                    break
                flags = next_byte | 0xFF00

            if flags & 1:  # Literal byte case
                byte = get_byte()
                if byte is None:
                    break
                buffer[r] = byte
                r = (r + 1) & buffer_size
                yield byte
            else:  # Compressed sequence case
                i = get_byte()
                j = get_byte()
                if i is None or j is None:
                    break

                i |= (j & 0xF0) << 4
                length = (j & 0x0F) + Lzs.THRESHOLD

                # Pre-calculate the buffer positions to minimize operations in the loop
                for k in range(length + 1):
                    buffer_pos = (i + k) & buffer_size
                    byte = buffer[buffer_pos]
                    buffer[r] = byte
                    r = (r + 1) & buffer_size
                    yield byte

            # Right-shift the flags for the next round
            flags >>= 1

def test_result():

    original_hex = bytes(
        b'\xF5\x10\xEB\xF0\x09\xEB\xF0\x0C\x04\x00\x00\xFF\x40\x01\xF0\x00\x00\x01\x02\x00\xFF\xFF\xFF\xFE\xFF\xFC\xFF\xDE\xFB\xFF\xFA\xFF\xF7\xFF\x9C\xF3\xF4\xFF\xFF\x7B\xEF\xF1\xFF\x5A'
    )
    expected_decoded_hex = bytes(
        b'\x10\x00\x00\x00\x09\x00\x00\x00\x0C\x04\x00\x00\x40\x01\xF0\x00\x00\x01\x02\x00\xFF\xFF\xFE\xFF\xFC\xFF\xDE\xFB\xFA\xFF\xF7\xFF\x9C\xF3\xF4\xFF\x7B\xEF\xF1\xFF\x5A'
    )
    lzs = Lzs()
    start_time = time.perf_counter()  # Start timing
    return_value = bytes(lzs.decode(input_bytes=original_hex))
    end_time = time.perf_counter()  # End timing
    print(f"Execution time: {end_time - start_time:.6f} seconds")

    # Print the result for debugging
    print("Decoded result:", return_value.hex(" "))
    print("Expected result:", expected_decoded_hex.hex(" "))
    # Check if the returned value matches the expected output
    print("Test passed:", return_value == expected_decoded_hex)
    return return_value == expected_decoded_hex

if __name__ == "__main__":
    test_result()