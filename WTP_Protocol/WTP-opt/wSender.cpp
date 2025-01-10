#include <iostream>
#include <string>
#include <fstream>
#include <cstring>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>
#include <chrono>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <packet.h>
#include <crc32.h>
#include <unordered_map>

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

std::ofstream mLog;
int mSocket;
sockaddr_in mAddr;

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

void sendPacket(Packet &packet)
{
    sendto(mSocket, &packet, sizeof(packet), 0, (struct sockaddr *)&mAddr, sizeof(mAddr));
    logPacket(packet);
}

bool receivePacket(Packet &packet)
{
    char buffer[MAX_PACKET_SIZE];
    sockaddr_in addressBuffer;
    socklen_t addressLength;
    int receivedLength = recvfrom(mSocket, buffer, MAX_PACKET_SIZE, MSG_DONTWAIT, (struct sockaddr *)&addressBuffer, &addressLength);
    if (receivedLength > 0)
    {
        Packet *receivedPacket = reinterpret_cast<Packet *>(buffer);
        packet = *receivedPacket;
        logPacket(packet);
        return validateChecksum(packet);
    }
    return false;
}

// the send logic for the sender
void processSend(Argument &args)
{
    mLog = std::ofstream(args.sender_log);
    if (!mLog.is_open())
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
    startPacket.header.checksum = crc32(&startPacket, sizeof(startPacket));

    bool startAckReceived = false;

    while (!startAckReceived)
    {
        // Send the START packet
        sendPacket(startPacket);

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
            Packet receivedPacketBuffer;
            if (receivePacket(receivedPacketBuffer))
            {
                if (receivedPacketBuffer.header.type == 3)
                {
                    startAckReceived = true;
                    break;
                }
            }
        }
    }

    bool finishedSending = false;
    int windowBase = 0;

    std::unordered_map<int, Packet> window;
    std::unordered_map<int, std::chrono::steady_clock::time_point> timeoutMap;
    std::unordered_map<int, bool> ackMap;
    while (!finishedSending)
    {
        finishedSending = window.empty() && inputFile.eof();

        // Send all packets in the window
        for (int i = windowBase; i < windowBase + args.window_size; i++)
        {
            // If already acked don't send
            if (ackMap.find(i) != ackMap.end() && ackMap[i])
                continue;

            // Only send packet if not sent before or has timedout
            if (timeoutMap.find(i) == timeoutMap.end() || std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - timeoutMap[i]).count() > TIMEOUT_MS)
            {
                Packet packet;

                // Create packet and store in window if not already in window
                if (window.find(i) == window.end())
                {
                    packet.header.type = 2;
                    packet.header.seqNum = i;
                    inputFile.read(packet.payload, MAX_PACKET_SIZE - sizeof(PacketHeader));
                    packet.header.length = inputFile.gcount();

                    // If no more data to read, stop sending new packets
                    if (packet.header.length == 0)
                    {
                        continue;
                    }

                    // Fill the header with checksum
                    packet.header.checksum = 0;
                    packet.header.checksum = crc32(&packet, sizeof(packet));
                    window[i] = packet;
                }
                else
                {
                    // Retrieve the packet from window
                    packet = window[i];
                }

                // Send the packet
                sendPacket(packet);

                // Store the sent timestamp
                timeoutMap[i] = std::chrono::steady_clock::now();
            }
        }

        // Receive ACKS IN WINDOW and slide window up consecutive received ack from base
        // But respond to ack even if it's not the next one from base (non sequential)
        Packet receivedPacketBuffer;
        if (receivePacket(receivedPacketBuffer))
        {
            // Validate that the received packet is an ACK
            if (receivedPacketBuffer.header.type == 3)
            {
                int receivedACK = receivedPacketBuffer.header.seqNum;

                // Only process ACK IN WINDOW
                if (receivedACK >= windowBase && receivedACK < windowBase + args.window_size)
                {
                    // Flag ack as received doesn't matter if it's the next expected (sequential)
                    ackMap[receivedACK] = true;
                    timeoutMap[receivedACK] = std::chrono::steady_clock::now();

                    // Try to slide window to the highest sequential received ACK from base
                    while (ackMap.find(windowBase) != ackMap.end() && ackMap[windowBase])
                    {
                        window.erase(windowBase);     // Remove from the window once acknowledged
                        timeoutMap.erase(windowBase); // Clean up timeout tracking
                        ackMap.erase(windowBase);     // Clean up ACK tracking
                        windowBase++;
                    }
                }
            }
        }
    }

    // Send END packet
    bool endACKReceived = false;

    while (!endACKReceived)
    {
        // Send END message
        Packet endPacket;
        endPacket.header.type = 1;
        endPacket.header.length = 0;
        endPacket.header.seqNum = 0;
        endPacket.header.checksum = 0;
        endPacket.header.checksum = crc32(&endPacket, sizeof(endPacket));
        sendPacket(endPacket);

        // END timer for the END packet
        auto endTime = std::chrono::steady_clock::now();
        while (!endACKReceived)
        {
            std::chrono::steady_clock::time_point currTime = std::chrono::steady_clock::now();
            auto durationMs = std::chrono::duration_cast<std::chrono::milliseconds>(currTime - endTime).count();

            if (durationMs > TIMEOUT_MS)
            {
                std::cerr << "Timeout waiting for ACK for END packet, retransmitting..." << std::endl;
                endTime = std::chrono::steady_clock::now();
                break;
            }

            // Try to receive ACK for the START packet
            Packet receivedPacketBuffer;
            if (receivePacket(receivedPacketBuffer))
            {
                if (receivedPacketBuffer.header.type == 3 && receivedPacketBuffer.header.seqNum == 0)
                {
                    endACKReceived = true;
                    break;
                }
            }
        }
    }

    mLog.close();
}

// main function for the Sender
int main(int argc, char *argv[])
{
    Argument args;
    parseArgument(argc, argv, args);

    // create the socket
    mSocket = createUDPSocket(args.receiver_IP, args.receiver_port, mAddr);

    // process the sending with a funnction
    processSend(args);

    close(mSocket);
    return 0;
}
