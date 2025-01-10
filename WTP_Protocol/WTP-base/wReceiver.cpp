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

void processReceive(Argument &args, int socket)
{
    std::ofstream log(args.receiver_log);
    if (!log.is_open())
    {
        std::cerr << "Failed to open log file" << std::endl;
        return;
    }

    bool startReceived = false;
    struct sockaddr_in senderAddr;
    socklen_t addrLength = sizeof(senderAddr);

    // Wait for START packet
    while (!startReceived)
    {
        Packet ackPacket;
        char buffer[MAX_PACKET_SIZE];
        memset(buffer, 0, sizeof(buffer));

        ssize_t receivedLength = recvfrom(socket, buffer, MAX_PACKET_SIZE, MSG_DONTWAIT, (struct sockaddr *)&senderAddr, &addrLength);
        if (receivedLength > 0)
        {
            Packet *_packet = reinterpret_cast<Packet *>(buffer);
            PacketHeader tempHeader = _packet->header;
            tempHeader.checksum = 0;
            unsigned int recvChecksum = crc32(&tempHeader, sizeof(tempHeader));

            if (_packet->header.type == 0 && recvChecksum == _packet->header.checksum)
            {
                std::cout << "Received START packet from sender" << std::endl;

                log << _packet->header.type << " " << _packet->header.seqNum << " "
                    << _packet->header.length << " " << _packet->header.checksum << std::endl;

                ackPacket.header.type = 3;
                ackPacket.header.seqNum = 0;
                ackPacket.header.length = 0;
                ackPacket.header.checksum = crc32(&ackPacket.header, sizeof(ackPacket.header));
                sendto(socket, &ackPacket, sizeof(ackPacket), 0, (struct sockaddr *)&senderAddr, sizeof(senderAddr));

                log << ackPacket.header.type << " " << ackPacket.header.seqNum << " "
                    << ackPacket.header.length << " " << ackPacket.header.checksum << std::endl;

                startReceived = true;
            }
        }
    }

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
            if (errno == EAGAIN || errno == EWOULDBLOCK)
                perror("Error receiving data packet");
            continue;
        }

        Packet *_packet = reinterpret_cast<Packet *>(buffer);

        // Process END packet
        if (_packet->header.type == 1)
        {
            finishedRecv = true;
            std::cout << "Received END packet. Transmission complete." << std::endl;
            break;
        }

        Packet tempPacket = *_packet;
        tempPacket.header.checksum = 0;

        // Validate data packet
        if (_packet->header.type == 2 && _packet->header.checksum == crc32(&tempPacket, sizeof(tempPacket)))
        {
            log << _packet->header.type << " " << _packet->header.seqNum << " "
                << _packet->header.length << " " << _packet->header.checksum << std::endl;

            int seqNum = _packet->header.seqNum;

            // Store packet in buffer if within window
            if (seqNum >= expectedSeqNum && seqNum < expectedSeqNum + args.window_size)
            {
                packetBuffer[seqNum] = *_packet;

                // Write all consecutive packets to the output file and move the window forward
                while (packetBuffer.find(expectedSeqNum) != packetBuffer.end())
                {
                    Packet &pkt = packetBuffer[expectedSeqNum];
                    outputFile.write(pkt.payload, pkt.header.length);
                    packetBuffer.erase(expectedSeqNum);
                    expectedSeqNum++;
                }
            }

            // Send cumulative ACK for the last consecutive packet received
            Packet ackPacket;
            ackPacket.header.type = 3;
            ackPacket.header.seqNum = expectedSeqNum;
            ackPacket.header.length = 0;
            ackPacket.header.checksum = crc32(&ackPacket.header, sizeof(ackPacket.header));

            log << ackPacket.header.type << " " << ackPacket.header.seqNum << " "
                << ackPacket.header.length << " " << ackPacket.header.checksum << std::endl;

            if (sendto(socket, &ackPacket, sizeof(ackPacket), 0, (struct sockaddr *)&senderAddr, sizeof(senderAddr)) < 0)
            {
                perror("Failed to send ACK");
            }
            else
            {
                std::cout << "Sent cumulative ACK for packet " << ackPacket.header.seqNum << std::endl;
            }
        }
    }

    outputFile.close();
    log.close();
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