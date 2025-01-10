#!/usr/bin/python3
from __future__ import print_function, division, absolute_import

import grp
import pwd
import shutil

import subprocess
import os
import time
import optparse
import sys
import signal
import re
import threading
from mininet.clean import Cleanup
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.topo import Topo
from mininet.cli import CLI
from subproc_util import time_procs
import psutil
import tempfile
import filecmp
from testdefs import mininet_base_test_attributes, mininet_opt_test_attributes

# Constants
currtime = time.strftime("-%Y%m%d-%H%M%S")
DEFAULT_LOG = "LOG" + currtime
DEFAULT_RECEIVER_PORT = 2333
PROXY_PORT = 5005
DEFAULT_SENDER_LOG = "SENDER" + currtime
DEFAULT_RECEIVER_LOG = "RECEIVER" + currtime
DEFAULT_SENDER_HOST_IDX = 0
DEFAULT_RECEIVER_HOST_IDX = 1
MIN_LOG_LINES = 5
MAX_LOG_LINES = 1000000
INTERVAL_TESTS_SECOND = 1

# Variables
num_total_tests = 0
num_passed = 0
total_points = 0
points_received = 0

# File paths
PROXY_SCRIPT = os.getcwd() + '/grader/udp_proxy.py'

# open /dev/null
FNULL = open(os.devnull, 'w')
FOUT = open('/tmp/out.txt', 'w')
FERR = open('/tmp/err.txt', 'w')

class SimpleNetwork0(Topo):
  def __init__(self, **opts):
    Topo.__init__(self, **opts)
    h1 = self.addHost('h1')
    h2 = self.addHost('h2')
    s1 = self.addSwitch('s1')
    self.addLink(h1, s1, bw=40, delay='0.1ms')
    self.addLink(h2, s1, bw=40, delay='0.1ms')

def remove_if_exists(path_to_file):
  if os.path.exists(path_to_file):
    try:
      os.remove(path_to_file)
    except:
      pass

def make_tempfile(content):
  fd, path = tempfile.mkstemp()
  with os.fdopen(fd, 'w') as tmp:
    tmp.write(content)
  return fd, path

def make_input0():
  content = "random short text\n"
  fd, path = make_tempfile(content)
  return fd, path

make_input_file = {
  "file0": make_input0
}

def handle_timeout(sender_proc, receiver_proc):
  #print("Calling handle_timeout")
  try:
    sender_proc.kill()
  except Exception as ex:
    #print("Exception in killing sender: {}".format(ex))
    pass
  
  try:
    receiver_proc.kill()
  except Exception as ex:
    #print("Exception in killing receiver: {}".format(ex))
    pass

  return

# identical to handle_timeout, except that test case is not treated as failed
def clean_procs(sender_proc, receiver_proc):
  #print("Calling clean_procs")
  try:
    sender_proc.kill()
    receiver_proc.kill()
  except Exception as ex:
    #print("Exception in killing sender: {}".format(ex))
    pass

  try:
    sender_proc.kill()
    receiver_proc.kill()
  except Exception as ex:
    #print("Exception in killing receiver: {}".format(ex))
    pass

  return

# policy are passed in by a list. Now support 'has_dupACK' and 'no_dupACK'

def verify_log(log, policy=None):
  #    print("@@@Calling verify_log")
  logline = 0
  has_START_pkt = False
  has_END_pkt = False
  has_ACK_pkt = False
  has_Dup_ACK = False
  has_dup_data = False  # to check re-transmission of data
  seen_acks = set()  # used to check Dup ACKs
  seen_datas = set()  # used to check re-transmission of data

  start_seq_num = -1  # The seqNum of START packet, we don't consider dup ACK on this seqNum
    # TODO change the spec so that START and END use different ACK packet

    # with open(log, "r") as logfile:
    # print("log:")
    # print(log)
  for line in log:

    logline += 1

    if logline > MAX_LOG_LINES:
      #print("\nERROR: too many log lines")
      return False
    # print("Log Line:" + line)
    items = line.split()

    try:
      found_type = items[0].strip()
      found_seq = items[1].strip()
      found_len = items[2].strip()
      found_checksum = items[3].strip()
      if not (found_type.isdigit() and found_seq.isdigit()
              and found_len.isdigit() and found_checksum.isdigit()):
        print("\nERROR: incorrect log format")
        return False

      pkt_type = int(found_type)
      pkt_seq = int(found_seq)
      pkt_len = int(found_len)
      pkt_cksm = int(found_checksum)

      # always check for START/END/ACK pkt
      if pkt_type == 0:
        start_seq_num = pkt_seq
        has_START_pkt = True

      # Check END pkt and check the seqNum == start_seqNum
      if pkt_type == 1:
        has_END_pkt = True
        #               if pkt_seq != start_seq_num:
        # TODO: After this semester, add multi-file test cases and enforce seqNum
        #                    print("WARNING: END packet seqNum != START")
        # return False

      if pkt_type == 3:
        has_ACK_pkt = True

        # Policy-based checking
      if policy is not None:
        # check Dup ACKs
        if ('has_dupACK' in policy or 'no_dupACK' in policy) and pkt_type == 3:
          # We don't consider dup ACK on start packet,
          # because END will have same seqNum and the ACK may be considered duplicate
          if pkt_seq != start_seq_num:
            if pkt_seq not in seen_acks:
              seen_acks.add(pkt_seq)
            else:
              has_Dup_ACK = True

          # Check re-transmission of data
        if ('has_reTrans' in policy or 'no_reTrans' in policy) and pkt_type == 2:
          if pkt_seq not in seen_datas:
            seen_datas.add(pkt_seq)
          else:
            has_dup_data = True

    except Exception as ex:
      print("\nException in verifying log lines: {}".format(ex))
      return False

  if logline < MIN_LOG_LINES:
    #print("ERROR: too few log lines")
    return False

  if not has_START_pkt:
    #print("ERROR: no start packets")
    return False

  if not has_END_pkt:
    #print("ERROR: no end packets")
    return False

  if not has_ACK_pkt:
    #print("ERROR: no ack packets")
    return False

    # Policy-based checking
  if policy is not None:
    if 'has_dupACK' in policy:
      if not has_Dup_ACK:
        #       print("ERROR: no duplicate ACK")
        return False

      if 'no_dupACK' in policy:
        if has_Dup_ACK:
          #      print("ERROR: has duplicate ACK")
          return False

      if 'has_reTrans' in policy:
        if not has_dup_data:
          #     print("ERROR: no duplicate Data")
          return False

      if 'no_reTrans' in policy:
        if has_dup_data:
          #    print("ERROR: has duplicate Data")
          return False

    # try:
    #    if policy == "strict":
    #    else:
    # except:
    #    return False

  return True

def run_mininet_test(test_type, test_num, tmpdir):
  global num_passed
  global num_total_tests
  global points_received
  global DNS_TEMP_INFILE
  global PROXY_SCRIPT
  global opts

  dir_path = os.getcwd()

  # based on test type, set test attributes and get binary path from dir path
  if test_type == "base":
    sender_binary = os.path.join(dir_path, "WTP-base/wSender")
    receiver_binary = os.path.join(dir_path, "WTP-base/wReceiver")
    current_test_attributes = mininet_base_test_attributes[test_num]
  else:
    sender_binary = os.path.join(dir_path, "WTP-opt/wSender")
    receiver_binary = os.path.join(dir_path, "WTP-opt/wReceiver")
    current_test_attributes = mininet_opt_test_attributes[test_num]

  test_duration = current_test_attributes['duration']
  sender_window = current_test_attributes['s_win']
  receiver_window = current_test_attributes['r_win']
  test_filename = current_test_attributes['filename']

  # Construct commands
  # use the temporary folder to store sender/receiver logs
  sender_log = os.path.join(tmpdir, DEFAULT_SENDER_LOG)
  sender_idx = DEFAULT_SENDER_HOST_IDX
  sender_ip = "10.0.0.{}".format(sender_idx + 1)
  receiver_log = os.path.join(tmpdir,DEFAULT_RECEIVER_LOG)
  receiver_idx = DEFAULT_RECEIVER_HOST_IDX
  receiver_ip = "10.0.0.{}".format(receiver_idx + 1)
  test_port = DEFAULT_RECEIVER_PORT
  test_output_dir = tmpdir + '/'

  # # make a temporary input file
  # fd, TEMP_INFILE = make_input_file[test_filename]()
  # with open(TEMP_INFILE, "r") as infile:
  #     lines = infile.readlines()
  #     print("input file:")
  #     print(lines)

  # Clean up leftover
  Cleanup.cleanup()

  # Create data network
  # topo = networks[test_network]()

  if opts.verbose:
    print("Starting network")
    
  # Always use SimpleNetwork0
  topo = SimpleNetwork0()
  net = Mininet(topo=topo, link=TCLink, autoSetMacs=True, autoStaticArp=True, cleanup=True)
  # Run network
  net.start()

  # get host1
  h1 = net.hosts[sender_idx]
  # Before start testing, tune network parameters
  if 'netem' in current_test_attributes:
    test_netem = current_test_attributes['netem']
    #print("Setting netem to " + test_netem)
    tc_output = h1.cmd('tc qdisc show dev', h1.defaultIntf())
    #print('BEFORE TC!! ' + tc_output)

    # handle_pattern = re.compile()
    match = re.search(r"parent \d+:\d*", tc_output)
    if match is not None:
      parent_str = tc_output[match.start(): match.end()]
      
      h1.cmd('tc qdisc change dev', h1.defaultIntf(), parent_str, 'netem', test_netem)
      tc_output = h1.cmd('tc qdisc show dev', h1.defaultIntf())
      #print('AFTER TC: ' + tc_output)
      pass

  # Build the commands to call
  proxy_proc = None
  receiver_cmd = [receiver_binary, test_port, receiver_window, test_output_dir, receiver_log]
  receiver_cmd = [str(arg) for arg in receiver_cmd]

  # Start proxy, if we need proxy
  if 'proxy_corrupt' in current_test_attributes:
    test_corrupt = current_test_attributes['proxy_corrupt']
    #print('current corrupt ', test_corrupt)

    proxy_cmd = [PROXY_SCRIPT, '--src-ip', sender_ip,
                 '--dst-ip', receiver_ip, '--dst-port', test_port,
                 '--port', PROXY_PORT, '--corrupt', test_corrupt]
    proxy_cmd = [str(arg) for arg in proxy_cmd]
    proxy_proc = net.hosts[sender_idx].popen(proxy_cmd, stdout=FNULL, stderr=FNULL)
    if opts.verbose:
      print("Proxy command: " + str(proxy_cmd))

    sender_cmd = [sender_binary,sender_ip, PROXY_PORT,sender_window, test_filename, sender_log]
    sender_cmd = [str(arg) for arg in sender_cmd]

  else:
    sender_cmd = [sender_binary,receiver_ip,test_port,sender_window,test_filename,sender_log]
    sender_cmd = [str(arg) for arg in sender_cmd]

  if opts.verbose:
    print("Sender_cmd:" + str(sender_cmd))
    print("Receiver_cmd:" + str(receiver_cmd))
    
  # Start receiver and sender proc
  receiver_proc = net.hosts[receiver_idx].popen(receiver_cmd, stdout=FNULL, stderr=FNULL)
  if opts.verbose:
    print("Started receiver, PID=", receiver_proc.pid)
  time.sleep(1)
  sender_proc = net.hosts[sender_idx].popen(sender_cmd, stdout=FNULL, stderr=FNULL)
  # sender_proc = net.hosts[sender_idx].popen(sender_cmd, stdout=FOUT, stderr=FERR)
  if opts.verbose:
    print("Started sender PID=", sender_proc.pid)

  if opts.cli:
    CLI(net) # For debug purpose
    return
    
  timer = threading.Timer(test_duration, handle_timeout, [sender_proc, receiver_proc])
  try:
    timer.start()
    # sender_out, sender_err = sender_proc.communicate()
    sender_proc.wait()
    # receiver_out, receiver_err = receiver_proc.communicate()
    receiver_proc.wait()
  finally:
    timer.cancel()
    # always need to kill sender/receiver proc
    clean_procs(sender_proc, receiver_proc)

  if sender_proc.returncode == -signal.SIGSEGV or receiver_proc.returncode == -signal.SIGSEGV:
    print("Segmentation Fault.\n")
    print("Sender code: {}, Receiver code: {}".format(sender_proc.returncode,
                                                      receiver_proc.returncode))
    net.stop()
    return 0

  # Start sender log processing
  log_policy = current_test_attributes.get('policy')

  if not os.path.exists(os.path.realpath(sender_log)):
    print("\nTest (" + str(num_total_tests) + ") failed.")
    print("Error finding sender log file.")

    net.stop()
    return 0

  try:
    # Try to verify sender log
    with open(os.path.realpath(sender_log), 'r') as user_log:
      log_string = user_log.read().splitlines()

      if not verify_log(log_string, policy=log_policy):
        print("\nTest (" + str(num_total_tests) + ") failed.")
        print("Log checking failed.")

        net.stop()
        return 0

  except Exception as ex:
    print("\nTest (" + str(num_total_tests) + ") failed.")
    print("Exception in verifying log file in Test ({}): {}".format(num_total_tests, ex))

    net.stop()
    return 0

  # Check if output file matches input file
  output_file_path = "{}FILE-0.out".format(test_output_dir)
  # First check file existence
  if not os.path.exists(output_file_path):
    print("Error finding output file: " + output_file_path)

    # remove_if_exists(TEMP_INFILE)
    net.stop()
    return 0

    # Assume for each test we are only recving one file, which means the file name is always "FILE-0.out"
  try:
    # print("comparing" + test_filename + ", " + "{}FILE-0.out".format(test_output_dir))
    if filecmp.cmp(test_filename, "{}FILE-0.out".format(test_output_dir)):
      num_passed += 1
      points_received += current_test_attributes.get('points')
      print("** PASSED test number " + str(test_num) + " with "
            + str(current_test_attributes.get('points')) + " points")
    else:
      print("\nTest (" + str(num_total_tests) + ") failed.")
      print("File checking failed")
  except Exception as e:
    print("Exception in comparing files.", str(e))

    net.stop()
    return 0

  return

def take_a_rest(wait_seconds):
  time.sleep(wait_seconds)
  return 0

def run_a_test(test_type, test_num):

  if test_type != "base" and test_type != "opt":
    print("Error: No such test type.")
    sys.exit(1)

  print("********* Running " + test_type + " test number: " + str(test_num) + "********")
  
  # Create tmpdir in old python 2.7 fashion. create tmpdir here to reduce code
  tmpdir = tempfile.mkdtemp()
  run_mininet_test(test_type, test_num, tmpdir)

  # Cleanup tmpdir
  try:
    shutil.rmtree(tmpdir)
  except Exception as ex:
    sys.stderr.write('Exception in removing tmpdir {} : {}\n'.format(tmpdir, ex))

  return 0

def search_pattern(pattern, file):
  for line in file.splitlines():
    if pattern in line:
      return True

  return False

def test_base():
  print("\n### Running all WTP-base tests.")

  for i in range(0, len(mininet_base_test_attributes)):
    run_a_test("base", i)
    take_a_rest(INTERVAL_TESTS_SECOND)

  return

def test_opt():
  print("\n### Running all WTP-opt tests.")

  for i in range(0, len(mininet_opt_test_attributes)):
    run_a_test("opt", i)
    take_a_rest(INTERVAL_TESTS_SECOND)

  return

def main():
  global opts
  global num_total_tests
  global num_passed
  global total_points

  if os.geteuid() != 0:
    print("You need to run the script as root. Exiting.")
    sys.exit(1)

  if not os.path.exists(PROXY_SCRIPT):
    print("Proxy script path: " + PROXY_SCRIPT)
    print("Invoke grader.py from top-level Assignment3 directory!")
    sys.exit(1)

  usage = "Usage: sudo ./grader.py [options]"
  parser = optparse.OptionParser(usage=usage)
  parser.add_option("-c", "--cli",
                    action="store_true",
                    dest="cli",
                    default=False,
                    help="Start the CLI for debugging.")
  parser.add_option("-v", "--verbose",
                    action="store_true",
                    dest="verbose",
                    default=False,
                    help="Print more information for debugging.")
  parser.add_option("-b", "--base",
                    dest="basenum",
                    default=None,
                    help="Run specified test number from base tests")
  parser.add_option("-o", "--opt",
                    dest="optnum",
                    default=None,
                    help="Run specified test number from optimizations tests")
  parser.add_option("-A", "--partA",
                    action="store_true",
                    dest="partA",
                    default=False,
                    help="Run WTP-base tests")
  parser.add_option("-B", "--partB",
                    action="store_true",
                    dest="partB",
                    default=False,
                    help="Run WTP-opt tests")
  (opts, args) = parser.parse_args()

  if opts.basenum:
    i = int(opts.basenum)
    if (i < len(mininet_base_test_attributes)):
      run_a_test("base", i)
    else:
      print('Base test number ' + str(i) + " out of range")
    return

  if opts.optnum:
    i = int(opts.optnum)
    if (i < len(mininet_opt_test_attributes)):
      run_a_test("opt", i)
    else:
      print('Opt test number: ' + str(i) + " out of range")
    return

  # perform_tests()
  if opts.partA:
    num_total_tests = len(mininet_base_test_attributes) 
    for i in range(0, len(mininet_base_test_attributes)):
      total_points += mininet_base_test_attributes[i]['points']
    test_base()

  if opts.partB:
    num_total_tests = len(mininet_opt_test_attributes)
    for i in range(0, len(mininet_opt_test_attributes)):
      total_points += mininet_opt_test_attributes[i]['points']
    test_opt()

  if opts.partA or opts.partB:
    print("\n###[SUMMARY]: PASSED " + str(num_passed) +
          " out of " + str(num_total_tests) + " tests.\n")
    print("\n###[POINTS]: " + str(points_received) + "/"
          + str(total_points) + "\n")
    
  return

if __name__ == "__main__":

  time_start = time.time()

  try:
    main()

  finally:
      # Cleanup
    os.system('sudo killall -q wSender wReceiver; sudo pkill -f udp_proxy.py')
    try:
      for child in psutil.Process().get_children(recursive=True):
        child.kill()
    except:
      pass

  time_elapsed = time.time() - time_start
  print('Elapsed time : ', time_elapsed)
