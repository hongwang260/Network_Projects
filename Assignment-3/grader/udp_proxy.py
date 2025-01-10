#!/usr/bin/env python3

from __future__ import print_function, division, absolute_import
import optparse
import random
import sys

"""
A UDP proxy that connects wSender and wReceiver, with features:
1. It can corrupt certain bits
2. It can drop certain packets (TODO)

Design: a single-threaded server that listens on one datagram socket.
It blocks on receiving packets. Upon receiving, it check the source IP and forward to the corresponding addresses.

Also, we don't know the socket port for wSender until we receive the first packet from it.
It then remembers the server port and will update it if we see a new port. 
(In this way some additional packet loss will be introduced if the wSender is switching socket ports)

"""

import socket
import logging

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


def manipulate_packet(data, opts):

    ret_data = data

    if options.corrupt is not None:

        # We only corrupt packets that has content, with some probability
        packet_len = len(data)
        if packet_len > 16:
            if random.random() < opts.corrupt:

                byte_to_change = random.randint(16, packet_len - 1)
                old_byte = int(data[byte_to_change])  # python2 do not support convert raw bytes to int
                new_byte = (old_byte + random.randint(25, 50)) % 256
                logger.info('Corrupting corrupt {} : content {!r} -> {}'.format(byte_to_change, old_byte, new_byte))
                ret_data = bytearray(data)
                ret_data[byte_to_change] = new_byte

                # data[byte_to_change] = int(data[byte_to_change]) + 1
    return bytes(ret_data)


def mainloop(opts):
    sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    proxy_addr = (opts.bind_address, opts.port)
    receiver_addr = (opts.dst_ip, opts.dst_port)
    sock_udp.bind(proxy_addr)
    sender_ip = opts.src_ip
    sender_port = -1

    while True:
        data, addr = sock_udp.recvfrom(4096)
        # print('receive')
        if not data:
            # logger.error('an error occured')
            continue
        # print('received: {0!r} from {1}'.format(data, addr))
        # print('received: from {0}'.format(addr))

        # First handle packets from receiver
        if addr == receiver_addr:
            # print('From receiver')

            # Only after we know the sender port, can we do anything with the packets from receiver
            if sender_port != -1:
                # process packets
                sent = sock_udp.sendto(data, (sender_ip, sender_port))
                # logger.info("Sent {} to sender @ {}".format(sent, (sender_ip, sender_port)))

            continue

        # Handle packet from sender
        if addr[0] == sender_ip:
            # print('From sender')
            sender_port = addr[1]
            # print('port {0}'.format(sender_port))

            # manipulate the packet
            data = manipulate_packet(data, options)
            sent = sock_udp.sendto(data, receiver_addr)
            # logger.info("Sent {} to receiver @ {}".format(sent, receiver_addr))

            continue

    sock_udp.close()


if __name__ == '__main__':

    parser = optparse.OptionParser()

    parser.add_option('--bind-address',
                      help='The address to bind, use 0.0.0.0 for all ip address.')
    parser.add_option('--port',
                      help='The port to listen, eg. 5001',
                      type=int)
    parser.add_option('--src-ip',
                      help='wSender host ip, eg. 10.0.0.1')
    parser.add_option('--dst-ip',
                      help='wReceiver host ip, eg. 10.0.0.2')
    parser.add_option('--dst-port',
                      help='wReceiver host port, eg. 6001',
                      type=int)

    parser.add_option('--corrupt',
                      help='percentage to corrupt the content of the packet, eg. 0.01 for 1%',
                      type=float)

    (options, args) = parser.parse_args()

    if args:
        print("Error: invalid input args.")
        parser.print_help()
        sys.exit(1)

    # if options.dst_ip is None:
    #     print("Error: invalid input args.")
    #     parser.print_help()
    #     sys.exit(1)

    if options.bind_address is None:
        options.bind_address = '0.0.0.0'
    print("Using {} as bind address".format(options.bind_address))

    if options.port is None:
        options.port = 5001
    print("Using {} as bind port".format(options.port))

    if options.src_ip is None:
        options.src_ip = "10.0.0.1"
    print("Using {} as src_ip".format(options.src_ip))

    if options.dst_ip is None:
        options.dst_ip = "10.0.0.2"
    print("Using {} as dst_ip".format(options.dst_ip))

    try:
        mainloop(options)
    except KeyboardInterrupt:
        exit(0)
