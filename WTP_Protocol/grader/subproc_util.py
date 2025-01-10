import subprocess
import time
import psutil


def run_cmd_in_subprocess(cmd, timeout, check_exit_code=True):
    '''
    Run a command in subprocess on localhost (not mininet).
    Return stdout if command finish within timeout.
    If timeout occurs, return None.
    :param cmd: The command to run
    :param timeout: Timeout value in seconds
    :return:
    '''
    # print("Running cmd {}".format(cmd))
    subproc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)

    successful = time_procs([subproc], timeout, check_exit_code)
    if not successful:
        return None
    return subproc.communicate()[0]


def time_procs(procs, timeout, check_exit_code=True):
    """Monitor processes exit codes and or time them out."""
    start_time = time.time()
    current_time = start_time
    delay = 1.0
    err_non_zero = "### One (or more) of the processes exited non-zero."
    err_timeout = "### One (or more) of the processes timed out."
    while True:
        # Note: proc.poll() returns an rcode, which could be 0 or None
        # 0 is good, means we're done. None or anything else is bad
        # which is why the conditional is the way it is
        all_done = all([proc.poll() is not None for proc in procs])
        timed_out = current_time - start_time > timeout
        if all_done and check_exit_code:
            statuses = [proc.poll() for proc in procs]
            for status in statuses:
                if status != 0:
                    print(err_non_zero)
                    return False
            return True
        elif all_done:
            return True
        elif timed_out:
            print(err_timeout)
            for proc in procs:
                if proc.poll() is None:
                    cleanup_proc(proc)
            return False
        time.sleep(delay)
        current_time = time.time()
    return True


def cleanup_proc(proc):
    """Clean process and its children, attempt to shutdown gracefully."""
    parent = psutil.Process(pid=proc.pid)
    for child in parent.children(recursive=True):
        shutdown_proc(child)

    # Could be the case the parent has already exited after killing
    # its children (brutal, I know haha), but kill the parent too just in case
    shutdown_proc(parent)


def shutdown_proc(proc):
    try:
        # print("\n### Sending SIGTERM to process {}"
        #       .format(proc.pid))
        proc.terminate()
        # Give time for process to clean up
        time.sleep(1)
        if psutil.pid_exists(proc.pid):
            # print("\n### Process still not dead sending SIGKILL {}"
            #       .format(proc.pid))
            proc.kill()
    except psutil.NoSuchProcess:
        # This exception is passed in psutil's documentation
        # Also do this in case the pid doesn't exist anymore/exited somehow
        pass
