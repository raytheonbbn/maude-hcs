import math
"""
Take the "derivative" of a bit list [b0, b1, b2...bn] defined as 
[b0^b1, b1^b2, ... b(n-1)^bn]

"""
def derive(bits):
    assert len(bits) != 0, "Can't derive an empty list"
    return [bits[i]^bits[i+1] for i in range(len(bits)-1)]

"""
Returns the list-of-bools binary representation of an integer, with MS bit first
"""
def int_to_bitlist(n, width):
    # converts n to a binary string, truncates the leading "0b", then converts the characters to bools
    return [c == '1' for c in format(n, f'0{width}b')]

"""
Returns the list-of-bools binary representation of an integer, with LS bit first
"""
def int_to_bitlist_rev(n, width):
    # converts n to a binary string, truncates the leading "0b", then reverses it and converts the characters to bools
    return int_to_bitlist(n, width)[::-1]

"""
The H1 function from Maude
"""
def H1(fl):
    return -(fl*math.log(fl, 2))

"""
The H function from Maude
"""
def H(fl):
    return H1(fl) + H1(1 - fl)

def p(bits):
    assert len(bits) != 0, "Can't find probability on an empty list"
    return sum(bits) / len(bits)

def monus(k,j):
    if k >= j:
        return k-j
    else:
        return 0

def shannon(bits):
    # Get the probability of bits being true
    fl = p(bits)
    if(fl == 0 or fl == 1):
        return 0
    else:
        return H(fl)
    
def biEn(bits):
    k = 0
    n = monus(len(bits), 1)
    fl = 0.0
    while n > 0:
        fl = fl + (shannon(bits) * (1 << k))
        bits = derive(bits)
        k += 1
        n -= 1
    return fl / ((1 << k) - 1)

def main():
    # test on 0b01010101
    assert (int_to_bitlist_rev(85, 8)) == [True, False, True, False, True, False, True, False]
    assert (derive(int_to_bitlist_rev(85, 8))) == [True, True, True, True, True, True, True]
    assert (derive(derive(int_to_bitlist_rev(85, 8)))) == [False, False, False, False, False, False]

    # Same tests as in Maude
    D0 = [True, False, True, True]
    D1 = derive(D0)
    D2 = derive(D1)

    print(H1(p(D0)))
    print(shannon(D0)*(1<<0))
    print(shannon(D1)*(1<<1))
    print(shannon(D2)*(1<<2))
    print(biEn(D0))
if __name__ == '__main__':
    main()

