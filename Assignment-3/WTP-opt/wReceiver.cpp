#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <unordered_map>
#include <cstring>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include "packet.h"
#include "crc32.h"
#include <set>

const int MAX_PACKET_SIZE = 1472;

// class that stores arguments from the command line
class Argument
{
public:
    int listening_port = 0;
    std::string output_dir = "";
    int window_size = 0;
    std::string receiver_log = "receiver_log.txt";
};

// class used to store log data
class LogData
{
public:
    unsigned int type = 0;
    unsigned int seqNum = 0;
    unsigned int length = 0;
    unsigned int checksum = 0;
};

std::ofstream mLog;

void parseArgument(int argc, char *argv[], Argument &args)
{
    if (argc < 5)
    {
        std::cerr << "Missing argument" << std::endl;
        exit(1);
    }

    args.listening_port = std::stoi(argv[1]);
    args.window_size = std::stoi(argv[2]);
    args.output_dir = argv[3];
    args.receiver_log = argv[4];
}

int createUDPSocket(int port)
{
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0)
    {
        perror("Socket creation failed");
        exit(EXIT_FAILURE);
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    {
        perror("Binding failed");
        close(sock);
        exit(EXIT_FAILURE);
    }

    return sock;
}

bool validateChecksum(Packet &packet)
{
    unsigned int checksum = packet.header.checksum;
    packet.header.checksum = 0;
    packet.header.checksum = crc32(&packet, sizeof(packet));
    return checksum == packet.header.checksum;
}

void logPacket(Packet &packet)
{
    mLog << packet.header.type << " " << packet.header.seqNum << " " << packet.header.length << " " << packet.header.checksum << std::endl;
}

void processReceive(Argument &args, int socket)
{
    mLog = std::ofstream(args.receiver_log);
    if (!mLog.is_open())
    {
        std::cerr << "Failed to open log file" << std::endl;
        return;
    }

    struct sockaddr_in senderAddr;
    socklen_t addrLength = sizeof(senderAddr);

    bool finishedRecv = false;
    int expectedSeqNum = 0;
    std::unordered_map<int, Packet> packetBuffer;

    std::ofstream outputFile(args.output_dir + "/FILE-0.out", std::ios::binary);

    while (!finishedRecv)
    {
        char buffer[MAX_PACKET_SIZE];
        memset(buffer, 0, sizeof(buffer));

        ssize_t receivedLength = recvfrom(socket, buffer, MAX_PACKET_SIZE, MSG_DONTWAIT, (struct sockaddr *)&senderAddr, &addrLength);
        if (receivedLength <= 0)
        {
            continue;
        }

        Packet *_packet = reinterpret_cast<Packet *>(buffer);
        logPacket(*_packet);

        // Validate packet corruption for all packets, including END
        if (validateChecksum(*_packet))
        {
            int seqNum = _packet->header.seqNum;
            // Process END packet
            if (_packet->header.type == 1 && _packet->header.seqNum == 0)
            {
                finishedRecv = true;
            }

            // Drop packet if outside N + WINDOW_SIZE
            if (seqNum < expectedSeqNum + args.window_size)
            {
                // Send back ACK
                Packet ackPacket;

                ackPacket.header.type = 3;
                ackPacket.header.seqNum = seqNum;
                ackPacket.header.length = 0;
                ackPacket.header.checksum = 0;
                ackPacket.header.checksum = crc32(&ackPacket, sizeof(ackPacket));

                sendto(socket, &ackPacket, sizeof(ackPacket), 0, (struct sockaddr *)&senderAddr, sizeof(senderAddr));
                logPacket(ackPacket);

                // Store packet into buffer if is data
                if (_packet->header.type == 2)
                {
                    packetBuffer[seqNum] = *_packet;

                    // Try to slide the window forward
                    while (packetBuffer.find(expectedSeqNum) != packetBuffer.end())
                    {
                        expectedSeqNum++;
                    }
                }
            }
        }
    }

    // Write buffer to output
    int outPtr = 0;
    while (packetBuffer.find(outPtr) != packetBuffer.end())
    {
        Packet &pkt = packetBuffer[outPtr];
        if (pkt.header.type == 2)
        {
            outputFile.write(pkt.payload, pkt.header.length);
        }
        outPtr++;
    }

    outputFile.close();
    mLog.close();
}

int main(int argc, char *argv[])
{
    Argument args;
    parseArgument(argc, argv, args);

    int listening_socket = createUDPSocket(args.listening_port);

    processReceive(args, listening_socket);

    close(listening_socket);
    return 0;
}