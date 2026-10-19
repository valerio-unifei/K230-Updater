import binascii


def chip_id():
    """Hex string of the K230 unique chip id."""
    import machine
    cid = machine.chipid()
    if isinstance(cid, (bytes, bytearray)):
        return binascii.hexlify(cid).decode()
    return "%x" % cid
