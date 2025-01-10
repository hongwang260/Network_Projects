# Assignment 3: Reliable Transport

<!-- markdown-toc start - Don't edit this section. Run M-x markdown-toc-refresh-toc -->
**Table of Contents**

- [Assignment 3: Reliable Transport](#assignment-3-reliable-transport)
    - [Overview](#overview)
    - [Before you begin](#before-you-begin)
        - [WTP Specification](#wtp-specification)
        - [Packet Size](#packet-size)
    - [Learning Outcomes](#learning-outcomes)
    - [Clarifications](#clarifications)
    - [Part 1: Implement `wSender`](#part-1-implement-wsender)
        - [Running `wSender`](#running-wsender)
        - [Logging](#logging)
    - [Part 2: Implement `wReceiver`](#part-2-implement-wreceiver)
        - [Running `wReceiver`](#running-wreceiver)
    - [Part 3: Optimizations](#part-3-optimizations)
    - [Important Notes](#important-notes)
    - [Submission Instructions](#submission-instructions)
    - [Testing and Grading](#testing-and-grading)
    - [Acknowledgements](#acknowledgements)

<!-- markdown-toc end -->

<a name="overview"></a>
## Overview

In this project, you will build a simple reliable transport protocol, WTP, **on top of UDP**. Your WTP implementation must provide inorder, reliable delivery of UDP datagrams in the presence of events like packet loss, delay, corruption, duplication, and reordering.

There are a variety of ways to ensure a message is reliably delivered from a sender to a receiver. You are to implement a sender (`wSender`) and a receiver (`wReceiver`) that follows the following WTP specification.

## Before you begin

- To make it easier for us to assign scores for the assignment, please fill out the name, email and other details of every group member in [this file](../whoarewe.txt). 

- You can use the VM you downloaded for Assignment-1. However, we'd recommend installing a fresh copy of the VM if you installed additional packages. Follow these [instructions](../vm_setup.md).

### WTP Specification
WTP sends data in the format of a header, followed by a chunk of data.

WTP has four header types: `START`, `END`, `DATA`, and `ACK`, all following the same format:

```
struct PacketHeader {
	unsigned int type;     // 0: START; 1: END; 2: DATA; 3: ACK
	unsigned int seqNum;   // Described below
	unsigned int length;   // Length of data; 0 for ACK, START and END packets
	unsigned int checksum; // 32-bit CRC
}
```

We have provided a definition of this struct in the file `PacketHeader.h` `starter_files` directory. 

To initiate a connection, `wSender` starts with a `START` message along with a random `seqNum` value, and wait for an ACK for this `START` message. After sending the `START` message, additional packets in the same connection are sent using the `DATA` message type, adjusting `seqNum` appropriately.(see below) After everything has been transferred, the connection should be terminated with `wSender` sending an `END` message with the same `seqNumq` as the `START` message, and waiting for the corresponding ACK for this message.

The ACK `seqNum` values for `START` and `END` messages should both be set to whatever the `seqNum` values are that were sent by `wSender`.

`wSender` will use **0** as the initial sequence number for data packets (corresponding to `DATA` packets) in that connection. Furthermore, `wReceiver` sends back cumulative `ACK` packets (described in more details below).

### Packet Size
An important limitation is the maximum size of your packets. The UDP protocol has an 8 byte header, and the IP protocol underneath it has a header of 20 bytes. Because we will be using Ethernet networks, which have a maximum frame size of 1500 bytes, this leaves 1472 bytes for your entire `packet` structure (including **both** the header and the chunk of data).

## Learning Outcomes

After completing this programming assignment, students should be able to:

* Explain the mechanisms required to reliably transfer data
* Describe how different sliding window protocols work

<a name="clarifications"></a>
## Clarifications

* Your program will only be tested with one wSender and one wReceiver for all parts.

<a name="part1"></a>
## Part 1: Implement `wSender`

`wSender` should read an input file and transmit it to a specified receiver using UDP sockets following the WTP protocol. It should split the input file into appropriately sized chunks of data, and append a `checksum` to each packet. `seqNum` should increment by one for each additional packet in a connection. Please use the 32-bit CRC header we provide in the `starter_files` directory, in order to add a checksum to your packet.

You will implement reliable transport using a sliding window mechanism. The size of the window (`window-size`) will be specified in the command line. `wSender` must accept cumulative `ACK` packets from `wReceiver`.

After transferring the entire file, you should send an `END` message to mark the end of connection.

`wSender` must ensure reliable data transfer under the following network conditions:

* Loss of arbitrary levels;
* Re­ordering of ACK messages;
* Duplication of any amount for any packet;
* Delay in the arrivals of ACKs.

To handle cases where `ACK` packets are lost, you should implement a 500 milliseconds retransmission timer to automatically retransmit packets that were never acknowledged.
Whenever the window moves forward (i.e., some ACK(s) are received and some new packets are sent out), you reset the timer. If after 500ms the window still has not advanced, you retransmit all packets in the window because they are all never acknowledged.

### Running `wSender`
`wSender` should be invoked as follows:

`./wSender <receiver-IP> <receiver-port> <window-size> <input-file> <log>`

* `receiver-IP` The IP address of the host that `wReceiver` is running on.
* `receiver-port` The port number on which `wReceiver` is listening.
* `window-size` Maximum number of outstanding packets.
* `input-file` Path to the file that has to be transferred. It can be a text as well as a binary file (e.g., image or video).
* `log` The file path to which you should log the messages as described below.

Example: `./wSender 10.0.0.1 8888 10 input.in log.txt`

*Note: for simplicity, arguments will appear exactly as shown above during testing and grading. Error handling with the arguments is not explicitly tested but is highly recommended. At the very least, printing the correct usage if something went wrong is worthwhile.*

### Logging
`wSender` should create a log of its activity. After sending or receiving each packet, it should append the following line to the log (i.e., everything except the `data` of the `packet` structure described earlier):

`<type> <seqNum> <length> <checksum>`

<a name="part2"></a>
## Part 2: Implement `wReceiver`

`wReceiver` needs to handle only one `wSender` at a time and should ignore `START` messages while in the middle of an existing connection. It must receive and store the file sent by the sender on disk completely and correctly; i.e., if it received a video file, we should be able to play it! The stored file should be named `FILE-i.out`, where `i=0` for the file from the first connection, `i=1` for the second, and so on.

`wReceiver` should also calculate the checksum value for the data in each `packet` it receives using the header mentioned in part 1. If the calculated checksum value does not match the `checksum` provided in the header, it should drop the packet (i.e. not send an ACK back to the sender).

For each packet received, it sends a cumulative `ACK` with the `seqNum` it expects to receive next. If it expects a packet of sequence number `N`, the following two scenarios may occur:

1. If it receives a packet with `seqNum` not equal to `N`, it will send back an `ACK` with `seqNum=N`.
2. If it receives a packet with `seqNum=N`, it will check for the highest sequence number (say `M`) of the in­order packets it has already received and send `ACK` with `seqNum=M+1`.

If the next expected `seqNum` is `N`, `wReceiver` will **drop** all packets with `seqNum` greater than or equal to `N + window-size` to maintain a `window-size` window.

`wReceiver` should also log every single packet it sends and receives using the same format as the `wSender` log.

### Running `wReceiver`
`wReceiver` should be invoked as follows:

`./wReceiver <port-num> <window-size> <output-dir> <log>`

* `port-num` The port number on which `wReceiver` is listening for data.
* `window-size` Maximum number of outstanding packets.
* `output-dir` The directory that the `wReceiver` will store the output files, i.e the `FILE-i.out` files.
* `log` The file path to which you should log the messages as described in [Part 1](#part1)

Example:
`./wReceiver 8888 2 /tmp log.txt`

*Note: for simplicity, arguments will appear exactly as shown above during testing and grading. Error handling with the arguments is not explicitly tested but is highly recommended. At least printing the correct usage if something went wrong is worthwhile.*

**All programs/code written for Part 1 and Part 2 of this assignment into a folder called `WTP-base`.**

<a name="part3"></a>
## Part 3: Optimizations

For this part of the assignment, you will be making a few modifications to the programs written in the previous two sections. Consider how the programs written in the previous sections would behave for the following case where there is a window of size 3:

<img src=".images/base_case.PNG" title="Inefficient transfer of data" alt="" width="250" height="250"/>

In this case `wReceiver` would send back two ACKs both with the sequence number set to 0 (as this is the next packet it is expecting). This will result in a timeout in `wSender` and a retransmission of packets 0, 1 and 2. However, since `wReceiver` has already received and buffered packets 1 and 2. Thus, there is an unnecessary retransmission of these packets.

In order to account for situations like this, you will be modifying your `wReceiver` and `wSender` accordingly. **You will save these different versions of the program in a folder called `WTP-opt`**:

* `wReceiver` will not send cumulative ACKs anymore; instead, it will send back an ACK with `seqNum` set to whatever it was in the data packet (i.e., if a sender sends a data packet with `seqNum` set to 2, `wReceiver` will also send back an ACK with `seqNum` set to 2). It should still drop all packets with `seqNum` greater than or equal to `N + window_size`, where `N` is the next expected `seqNum`.
* `wSender` must maintain information about all the ACKs it has received in its current window and maintain an individual timer for each packet. So, for example, packet 0 having a timeout would not necessarily result in a retransmission of packets 1 and 2.

For a more concrete example, here is how your improved `wSender` and `wReceiver` should behave for the case described at the beginning of this section:

<img src=".images/improvement.PNG" title="only ACK necessary data" alt="" width="250" height="250"/>

`wReceiver` individually ACKs both packet 1 and 2.

<img src=".images/improvement_2.PNG" title="only send unACKd data" alt="" width="250" height="250"/>

`wSender` receives these ACKs and denotes in its buffer that packets 1 and 2 have been received. Then, the it waits for the 500 ms timeout and only retransmits packet 0 again.

The command line parameters passed to these new `wSender` and `wReceiver` are the same as the previous two sections.

<a name="tips"></a>
## Important Notes
* It is up to you how you choose to read from and write to files, but you may find the `std::ifstream.read()` and `std::ofstream.write()` functions particularly helpful.
* Please closely follow updates on Piazza. All further clarifications will be posted on Piazza via pinned Instructor Notes. We recommend you follow these notes to receive updates in time.
* You **MUST NOT** use TCP sockets.
* You can find an example of UDP socket programming in the Discussion folder.
* Another good resource for UDP socket programming is [Beej's Guide to Network Programming Using Internet Sockets](https://beej.us/guide/bgnet/html/index.html).

<a name="submission-instr"></a>
## Submission Instructions

To submit: 

```
	$ git commit -a -m 'Assignment 3 submission'
    $ git push
```

Your assigned repository must contain:

* `Makefile`(s) to compile both executables with one single `make` command
* The source code for `wSender` and `wReceiver` from parts 1 and 2: all source files should be in a folder called `WTP-base`.
  * Subdirectories for source code within `WTP-base` are perfectly fine, as long as the executables are present after running `make` in `WTP-base`
* The source code for `wSender` and `wReceiver` from part 3: all source files should be in a folder called `WTP-opt`. Subdirectories are fine here too.
* A `README` file with the names and umich uniqnames of the group members.
* You should **not** modify files in any directory other than `WTP-base` and `WTP-opt`.

Example final structure of repository:
```
├── README.md
├── WTP-base
│   ├── Makefile <- supports "make clean" and "make"
│   ├── wReceiver <- Binary executable present after running "make"
│   ├── ** source c or cpp files **
│   └── wSender <- Binary executable present after running "make"
├── WTP-opt
│   ├── Makefile <- supports "make clean" and "make"
│   ├── wReceiver <- Binary executable present after running "make"
│   ├── ** source c or cpp files **
│   └── wSender <- Binary executable present after running "make"
└── starter_files
    ├── PacketHeader.h
    └── crc32.h
```

<a name="autograder"></a>
## Testing and Grading

In the `grader` directory, we provide a grading script that you can use to test your code and determine how many points you will get in this assignment.

To determine your points, we will pull your repository and run the following commands from the top-level `Assignment-3` directory:

```
% cd WTP-base
% make
% cd ../WTP-opt
% make
% cd ..
% sudo grader/grader.py
```

Before you submit, you should double-check that these commands work on your repository.

The grader has several options that you may find useful while debugging/testing:
* `-c`: drops you into the Mininet CLI
* `-v`: that prints the command line args we use for the tests
* `-b <num>`: runs **only** the base test <num>
* `-o <num>`: runs **only** the opt test <num>

> While running some of the tests you may see a warning in the console which suggests `Consider r2q change`. This is expected and should not affect your results.

## Acknowledgements

This programming assignment is based on UC Berkeley's Project 2 from EE 122: Introduction to Communication Networks.
