# Mininet Test cases, simple file transfer test under different link conditions
# The delay here is RTT

import os

TESTS_DIR = os.getcwd() + "/grader/test_files/"

mininet_base_test_attributes = [

    # Test 1 # Basic test
    {'duration': 2, 's_win': 1, 'r_win': 1, 'points' : 10,
     'filename': TESTS_DIR + 'rand16k', 'netem': 'delay 1ms'},

    # Test 2 # High latency: timeout (500ms) > RTT (delay)
    {'duration': 2, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand32k', 'netem': 'delay 300ms'},

    # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand32k', 'netem': 'delay 200ms'},

    # Test 3 # RTT > timeout, then all packets will be lost, then for 12 packets, 10s is enough
  # Here the window_size must be smaller than 12.
    {'duration': 10, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand16k', 'netem': 'delay 600ms'},
  # TODO need have more fine grained testing, so that students must implement timeout correctly.

    # Test 4 # Big file with duplicates, This case is too easy
  # TODO Change me: Uncomment the following test cases, because duplicate packet inside window leads to dup ACK!
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms duplicate 10%', 'policy': ['has_dupACK', 'no_reTrans']},
    
    {'duration': 2, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms duplicate 10%'},

    # Test 5 # Big file high loss. 512kB = 351 pkts, meaning 18 loss packets, 9s delay in dealing with loss packets.
  # < 14 pkts = 56% < 20 pkts = 95% .... # if we change it to 3% loss rate then < 20 pkts = 99.7%
    
    {'duration': 10, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms loss 3%', 'policy': ['has_dupACK']},

    # Test 6 # Big file high corrupt
    {'duration': 10, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 0.1ms',
     'policy': ['has_dupACK'], 'proxy_corrupt': 0.03},

    # Test 7 # Huge file big window, the througput constraint is loose here. 4MB/s is achievable for Yiwen.
    {'duration': 4, 's_win': 100, 'r_win': 100, 'points' : 10,
     'filename': TESTS_DIR + 'rand4M', 'netem': 'delay 0.1ms'},

    # Test 8, 9 # 1.4*200/0.001 = 280MB/s We test incrementally to see if they can achive 2MB/s TODO try increase delay?
    {'duration': 3, 's_win': 200, 'r_win': 200, 'points' : 10,
     'filename': TESTS_DIR + 'rand4M', 'netem': 'delay 1ms'},
    
    {'duration': 6, 's_win': 200, 'r_win': 200, 'points' : 10,
     'filename': TESTS_DIR + 'rand8M', 'netem': 'delay 1ms'},

    # Packet re-order test, If we let receiver window >= sender window, then receiver should not discard any packet.
  # Test 10, 11 # rate = 1.4M because of  1.4k*5/0.005
    {'duration': 2, 's_win': 5, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 2ms reorder 20% 20%',
     'policy': ['has_dupACK', 'no_reTrans']},

    {'duration': 2, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms reorder 10% 10%',
     'policy': ['has_dupACK', 'no_reTrans']},

    # Different window size test
  # {'duration': 4, 's_win': 10, 'r_win': 20, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms'},
  # Test 12
    {'duration': 4, 's_win': 20, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms'},

    # Followings are the test cases that we sometimes fail:

    # The following two RTT test cases we can't pass.
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand16k', 'netem': 'delay 600ms'},
  # 14k / 0.4 = 35 kbps, so expected duration is 1s
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand32k', 'netem': 'delay 400ms'},

    # # # Different window size test sometimes fail this test. Failure rate (Yiwen's base: 0.5%, opt: 3.5%)
  # Explanation: loss and timeout contributes to not finishing in time
  # {'duration': 2, 's_win': 4, 'r_win': 2, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms loss 1%'},
  # This also sometimes fail. Failure rate (Yiwen's base: 1%)
  # {'duration': 2, 's_win': 2, 'r_win': 4, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms loss 1%'},

]


mininet_opt_test_attributes = [

    # Basic test # NO basic test needed for WTP-opt
  # {'duration': 2, 's_win': 1, 'r_win': 1, 'filename': TESTS_DIR + 'rand16k', 'netem': 'delay 1ms'},

    # High latency: timeout (500ms) > RTT (delay)
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand32k', 'netem': 'delay 300ms'},
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand32k', 'netem': 'delay 200ms'},

    # Big file with duplicates. Duplicate is too easy, removing
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms duplicate 10%'},

    # Different window size test, easy so put in the front, Removed because WTP-base can pass.
  # {'duration': 4, 's_win': 10, 'r_win': 20, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms'},
  # {'duration': 4, 's_win': 20, 'r_win': 10, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms'},

    # Big file medium loss. we don't check has_reTrans here, because loss is not too high.
  # 13
    {'duration': 8, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms loss 2%', 'policy': ['no_dupACK']},

    # Big file high loss. 512kB = 351 pkts, meaning 14 loss packets, meaning 7s delay in dealing with loss packets.
  # FIXME: no need to enforce retransmission here.
  # 14
    {'duration': 10, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms loss 3%', 'policy': ['no_dupACK']},

    # Big file medium corrupt. we don't check has_reTrans here, because loss is not too high.
  # 15
    {'duration': 8, 's_win': 10, 'r_win': 10, 'points' : 10,
     'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 0.1ms',
     'policy': ['no_dupACK'], 'proxy_corrupt': 0.02},

    # Big file high corrupt
  # FIXME: no need to enforce retransmission here.
  # 16
     {'duration': 10, 's_win': 10, 'r_win': 10, 'points' : 10,
      'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 0.1ms',
      'policy': ['no_dupACK'], 'proxy_corrupt': 0.03},

    # Huge file big window, the througput constraint is loose here. 4MB/s is achievable for Yiwen.
  # {'duration': 4, 's_win': 100, 'r_win': 100, 'filename': TESTS_DIR + 'rand4M', 'netem': 'delay 0.1ms'},

    # 1.4*200/0.001 = 280MB/s We test incrementally to see if they can achive 2MB/s. Removed WTP-base can pass
  # {'duration': 2, 's_win': 200, 'r_win': 200, 'filename': TESTS_DIR + 'rand4M', 'netem': 'delay 1ms'},
  # {'duration': 4, 's_win': 200, 'r_win': 200, 'filename': TESTS_DIR + 'rand8M', 'netem': 'delay 1ms'},

    # {'duration': 10, 's_win': 100, 'r_win': 100, 'filename': TESTS_DIR + 'rand16M', 'netem': 'delay 0.1ms'},
  # {'duration': 10, 's_win': 200, 'r_win': 200, 'filename': TESTS_DIR + 'rand16M', 'netem': 'delay 0.1ms'},

    # Packet re-order test, same as base, except for no dupACK
  # 17
     {'duration': 2, 's_win': 5, 'r_win': 10, 'points' : 10,
      'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 2ms reorder 20% 20%',
      'policy': ['no_dupACK', 'no_reTrans']},
  # 18
     {'duration': 2, 's_win': 5, 'r_win': 5, 'points' : 10,
      'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 2ms reorder 20% 20%',
      'policy': ['no_dupACK', 'no_reTrans']}, 
  # 19
     {'duration': 2, 's_win': 10, 'r_win': 10, 'points' : 10,
      'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms reorder 10% 10%',
      'policy': ['no_dupACK', 'no_reTrans']},

    # We don't test re-order with duplicates because duplicate cause dupACK.
  # Re-order with larger file
  # 20
     {'duration': 2, 's_win': 10, 'r_win': 10, 'points' : 10,
      'filename': TESTS_DIR + 'rand512k', 'netem': 'delay 1ms reorder 10% 10%',
      'policy': ['no_dupACK', 'no_reTrans']},

    # Followings are the test cases that we sometimes fail:

    # The following two RTT test cases we can't pass.
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand16k', 'netem': 'delay 600ms'},
  # 14k / 0.4 = 35 kbps, so expected duration is 1s
  # {'duration': 2, 's_win': 10, 'r_win': 10, 'filename': TESTS_DIR + 'rand32k', 'netem': 'delay 400ms'},

    # # # Different window size test sometimes fail this test. Failure rate (Yiwen's base: 0.5%, opt: 3.5%)
  # Explanation: loss and timeout contributes to not finishing in time
  # {'duration': 2, 's_win': 4, 'r_win': 2, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms loss 1%'},
  # This also sometimes fail. Failure rate (Yiwen's base: 1%)
  # {'duration': 2, 's_win': 2, 'r_win': 4, 'filename': TESTS_DIR + 'rand128k', 'netem': 'delay 1ms loss 1%'},

]
