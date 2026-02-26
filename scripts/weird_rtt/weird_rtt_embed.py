import random
import time
import bientropy

"""
Returns the lower 8 bits of the input

Args:
    n(int):             The data
"""
def low8(n):
    return ((n >> 8) << 8) ^ n

"""
Returns a deterministically random byte seeded by a given value

Args:
    seed(int):          The seed for the RNG (not necessarily 8 bits)
"""
def get_seeded_randbyte(seed):
    return random.Random(seed).getrandbits(8)


"""
Embeds a byte of data, salted with a provided value, 
in the lower 8 bits of a 64-bit timestamp.

Args:
    timestamp(int):     The 64-bit timestamp.
    seed(int):          Seed for the RNG to generate the salt
    data(int):          The 8-bit data to be embedded.

Returns:
    int: The weird timestamp with embedded salted data
"""
def rtt_embed(timestamp, seed, data):
    assert (timestamp.bit_length() <= 64),"timestamp is not 64 bits"
    assert (data.bit_length() <= 8),"data is not 8 bits"
    
    salt = get_seeded_randbyte(seed)
    # data ^ salt should already be 8 bits, but doing this to be faithful to the Maude model
    return (low8(data ^ salt) ^ ((timestamp >> 8) << 8))

"""
Extracts a byte of data, which was salted with a provided value, 
from the lower 8 bits of a 64-bit timestamp.

Args:
    timestamp(int):     The 64-bit timestamp.
    seed(int):          The 8-bit seed which generated the salt originally XORed with the data.

Returns:
    int: The 8-bit data output
"""
def rtt_extract(timestamp, seed):
    assert (timestamp.bit_length() <= 64),"timestamp is not 64 bits"
    salt = get_seeded_randbyte(seed)
    return (low8(timestamp) ^ low8(salt))

"""
Gives a 64-bit timestamp

Returns:
    int:                The current time, represented as a 64-bit timestamp (arbitrarily choosing microseconds since 1970)
"""
def time64b():
    return int(time.time()*1000000)


"""
Calculates the entropy of a given timestamp for a number of least significant bits

Args:
    ts:             The timestamp
    n:              The number of least significant bits of the timestamp to use in the calculation

Returns:
    float:          The floating-point entropy value
"""
def tsEntropy(ts, n):
    bits = (bientropy.int_to_bitlist(ts, n))
    return bientropy.biEn(bits[len(bits)-n:])

def main():
    time_now = time64b()
    for data in range(256):
        for seed in range(256):
            weird_ts = rtt_embed(time_now, seed, data)
            extracted = rtt_extract(weird_ts, seed)
            assert (data == extracted), f"Extract doesn't match for data {data} salt {seed}"

    # Testing the entropy calculation
    assert (tsEntropy(13, 8)) == 0.9532158402497686
    assert (tsEntropy(13, 4)) == 0.9496956846525875
    assert (tsEntropy(211, 8)) == 0.9506424806924296
    assert (tsEntropy(211, 4)) == 0.4052273811584256
    assert (tsEntropy(9876, 32)) == 0.4729189023154678
    assert (tsEntropy(9876, 8)) == 0.9512928864313808
    assert (tsEntropy(4294967296123, 32)) == 0.4597407961067579
    assert (tsEntropy(4294967296123, 8)) == 0.45624114838874175
    
    print("All tests pass")





    

if __name__ == "__main__":
    main()