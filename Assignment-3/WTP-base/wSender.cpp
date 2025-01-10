#include <iostream>
#include <string>
#include <fstream>
#include <cstring>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>
#include <chrono>
#include <vector>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <packet.h>
#include <crc32.h>
const int MAX_PACKET_SIZE = 1472;
const int TIMEOUT_MS = 500; // Retransmission timeout in milliseconds

// class that stores arguments from the command line
class Argument
{
public:
    std::string receiver_IP = "";
    int receiver_port = 0;
    std::string input_file = "";
    int window_size = 0;
    std::string sender_log = "sender_log.txt";
};

// class used to store log datas
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
    // check if we have the correct number of arguments
    if (argc < 6)
    {
        std::cerr << "Missing argument" << std::endl;
        exit(1);
    }

    // correctly stores the arguments
    args.receiver_IP = argv[1];
    args.receiver_port = std::stoi(argv[2]);
    args.window_size = std::stoi(argv[3]);
    args.input_file = argv[4];
    args.sender_log = argv[5];
}

// Function to initialize and create a UDP socket
int createUDPSocket(const std::string &receiver_IP, int receiver_port, sockaddr_in &receiver_addr)
{
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0)
    {
        perror("Socket creation failed");
        exit(EXIT_FAILURE);
    }

    memset(&receiver_addr, 0, sizeof(receiver_addr));
    receiver_addr.sin_family = AF_INET;
    receiver_addr.sin_port = htons(receiver_port);

    if (inet_pton(AF_INET, receiver_IP.c_str(), &receiver_addr.sin_addr) <= 0)
    {
        perror("Invalid receiver IP address");
        close(sock);
        exit(EXIT_FAILURE);
    }

    if (connect(sock, (struct sockaddr *)&receiver_addr, sizeof(receiver_addr)) < 0)
    {
        perror("Connection to receiver failed");
        close(sock);
        exit(EXIT_FAILURE);
    }

    return sock;
}

// the send logic for the sender
void processSend(Argument &args, int socket, sockaddr_in &receiverAddr)
{
    LogData logInfo;
    std::ofstream log(args.sender_log);
    if (!log.is_open())
    {
        std::cerr << "Failed to open log file" << std::endl;
        return;
    }

    // Open input file
    std::ifstream inputFile(args.input_file, std::ios::binary);
    if (!inputFile.is_open())
    {
        std::cerr << "Failed to open input file!" << std::endl;
        exit(1);
    }

    // Send START packet
    Packet startPacket;
    startPacket.header.type = 0;
    startPacket.header.seqNum = 0;
    startPacket.header.length = 0;
    startPacket.header.checksum = 0;
    startPacket.header.checksum = crc32(&startPacket.header, sizeof(startPacket.header));

    bool startAckReceived = false;

    while (!startAckReceived)
    {
        // Send the START packet
        int bytesSend = sendto(socket, &startPacket, sizeof(startPacket), 0, (struct sockaddr *)&receiverAddr, sizeof(receiverAddr));
        std::cout << "Sent: " << bytesSend << std::endl;
        // Log START packet
        logInfo.checksum = startPacket.header.checksum;
        logInfo.length = startPacket.header.length;
        logInfo.seqNum = startPacket.header.seqNum;
        logInfo.type = startPacket.header.type;
        log << logInfo.type << " " << logInfo.seqNum << " " << logInfo.length << " " << logInfo.checksum << std::endl;

        // Start timer for the START packet
        auto startTime = std::chrono::steady_clock::now();
        while (true)
        {
            std::chrono::steady_clock::time_point currTime = std::chrono::steady_clock::now();
            auto durationMs = std::chrono::duration_cast<std::chrono::milliseconds>(currTime - startTime).count();

            if (durationMs > TIMEOUT_MS)
            {
                std::cerr << "Timeout waiting for ACK for START packet, retransmitting..." << std::endl;
                startTime = std::chrono::steady_clock::now(); // Reset startTime before retransmitting
                break;                                        // Break to resend the START packet
            }

            // Try to receive ACK for the START packet
            char buffer[MAX_PACKET_SIZE];
            socklen_t receiverAddrLength;
            int receivedLength = recvfrom(socket, buffer, MAX_PACKET_SIZE, MSG_DONTWAIT, (struct sockaddr *)&receiverAddr, &receiverAddrLength);
            if (receivedLength > 0)
            {
                Packet *receivedPacket = reinterpret_cast<Packet *>(buffer);
                if (receivedPacket->header.type == 3 && receivedPacket->header.seqNum == 0)
                {
                    startAckReceived = true;
                    std::cout << "Received ACK for START packet" << std::endl;

                    // Log ACK packet for START
                    logInfo.checksum = receivedPacket->header.checksum;
                    logInfo.length = receivedPacket->header.length;
                    logInfo.seqNum = receivedPacket->header.seqNum;
                    logInfo.type = receivedPacket->header.type;
                    log << logInfo.type << " " << logInfo.seqNum << " " << logInfo.length << " " << logInfo.checksum << std::endl;
                    break;
                }
            }
        }
    }

    bool finishedSending = false;
    int windowBase = 0;
    int nextSequenceNum = 0;
    std::vector<Packet> window(args.window_size);

    while (!finishedSending || windowBase < nextSequenceNum)
    {
        // Send packets in the window
        while (nextSequenceNum < windowBase + args.window_size)
        {
            Packet packet;
            packet.header.type = 2;
            packet.header.seqNum = nextSequenceNum;
            inputFile.read(packet.payload, MAX_PACKET_SIZE - sizeof(PacketHeader));
            packet.header.length = inputFile.gcount();

            // If no more data to read, stop sending new packets
            if (packet.header.length == 0)
            {
                finishedSending = true;
                break;
            }

            // Fill the header with checksum
            packet.header.checksum = 0;
            packet.header.checksum = crc32(&packet, sizeof(packet));

            // Store packet in the window
            window[nextSequenceNum % args.window_size] = packet;

            // Send the packet
            sendto(socket, &packet, sizeof(packet), 0, (struct sockaddr *)&receiverAddr, sizeof(receiverAddr));

            // Log DATA packet
            logInfo.checksum = packet.header.checksum;
            logInfo.length = packet.header.length;
            logInfo.seqNum = packet.header.seqNum;
            logInfo.type = packet.header.type;
            log << logInfo.type << " " << logInfo.seqNum << " " << logInfo.length << " " << logInfo.checksum << std::endl;

            nextSequenceNum++;
        }

        // Wait for ACKs, retransmitting if necessary
        auto startTime = std::chrono::steady_clock::now();
        bool ackReceived = false;
        char buffer[sizeof(Packet)];

        while (!ackReceived)
        {
            std::chrono::steady_clock::time_point currTime = std::chrono::steady_clock::now();
            auto durationMs = std::chrono::duration_cast<std::chrono::milliseconds>(currTime - startTime).count();

            if (durationMs > TIMEOUT_MS)
            {
                std::cerr << "Timeout waiting for ACKs, retransmitting window..." << std::endl;
                break;                                        // Break to retransmit the window
            }

            // Receive ACK
            // memset(buffer, 0, sizeof(buffer));
            socklen_t receiverAddrLength;
            int receivedLength = recvfrom(socket, buffer, MAX_PACKET_SIZE, MSG_DONTWAIT, (struct sockaddr *)&receiverAddr, &receiverAddrLength);
            if (receivedLength > 0)
            {
                Packet *receivedPacket = reinterpret_cast<Packet *>(buffer);

                // Validate that the received packet is an ACK
                if (receivedPacket->header.type == 3)
                {
                    int receivedACK = receivedPacket->header.seqNum;
                    if (receivedACK >= windowBase)
                    {
                        windowBase = receivedACK;
                        ackReceived = true;

                        // Log ACK packet
                        logInfo.checksum = receivedPacket->header.checksum;
                        logInfo.length = receivedPacket->header.length;
                        logInfo.seqNum = receivedPacket->header.seqNum;
                        logInfo.type = receivedPacket->header.type;
                        log << logInfo.type << " " << logInfo.seqNum << " " << logInfo.length << " " << logInfo.checksum << std::endl;

                        // Reset timer since we received a valid ACK
                        // startTime = std::chrono::steady_clock::now();
                        std::cout << "Received ACK: " << receivedACK << std::endl;
                    }
                }
            }
        }

        // Retransmit all packets in the window if ACK was not received
        if (!ackReceived)
        {
            for (int i = windowBase; i < nextSequenceNum; i++)
            {
                Packet &p = window[i % args.window_size];
                sendto(socket, &p, sizeof(p), 0, (struct sockaddr *)&receiverAddr, sizeof(receiverAddr));

                // Log retransmission of packet
                logInfo.checksum = p.header.checksum;
                logInfo.length = p.header.length;
                logInfo.seqNum = p.header.seqNum;
                logInfo.type = p.header.type;
                log << logInfo.type << " " << logInfo.seqNum << " " << logInfo.length << " " << logInfo.checksum << std::endl;
                std::cout << "Retransmitted packet: " << p.header.seqNum << std::endl;
            }
            startTime = std::chrono::steady_clock::now();
        }
    }

    // Send END message after all data is sent
    Packet endPacket;
    endPacket.header.type = 1;
    endPacket.header.length = 0;
    endPacket.header.seqNum = 0;
    endPacket.header.checksum = crc32(&endPacket, sizeof(endPacket));
    sendto(socket, &endPacket, sizeof(endPacket), 0, (struct sockaddr *)&receiverAddr, sizeof(receiverAddr));

    logInfo.checksum = endPacket.header.checksum;
    logInfo.length = endPacket.header.length;
    logInfo.seqNum = endPacket.header.seqNum;
    logInfo.type = endPacket.header.type;
    log << logInfo.type << " " << logInfo.seqNum << " " << logInfo.length << " " << logInfo.checksum << std::endl;
    std::cout << "Sent END packet!" << std::endl;

    log.close();
}

// main function for the Sender
int main(int argc, char *argv[])
{
    Argument args;
    parseArgument(argc, argv, args);

    sockaddr_in receiverAddr;
    // create the socket
    int UDP_socket = createUDPSocket(args.receiver_IP, args.receiver_port, receiverAddr);

    // process the sending with a funnction
    processSend(args, UDP_socket, receiverAddr);

    close(UDP_socket);
    return 0;
}
