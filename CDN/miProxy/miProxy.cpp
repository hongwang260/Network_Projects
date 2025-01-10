
#include <string>
#include <fstream>
#include <iostream>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#include <netdb.h>
#include <cstring>
#include <map>
#include <algorithm>
#include <sstream>
#include <vector>
#include <ctime>
#include <chrono>
#include "DNS/DNSMessage.h"
#include "DNS/DNSDomainName.h"

class Argument
{
public:
    std::string proxy_host = "";
    int proxy_port = 0;
    std::string upstream_host_ip = "";
    std::string upstream_host_name = "";
    int upstream_port = 0;
    double adap_gain = 0;
    double adap_multiplier = 0;
    std::string nameserver_ip = "";
    int nameserver_port = 0;
    std::string log_file_name = "log.txt";
};

class ClientState
{
public:
    std::vector<char> buf;
    int contentLength = 0;
    int totalBytes = 0;
    bool gotHeader = false;
    std::vector<int> clientSockets;
};

class ManifestArgs
{
public:
    int bandwidth = 0;
    std::string qualityName = "";
};

// data used for logging info
class LogData
{
public:
    std::chrono::steady_clock::time_point startTime;
    std::chrono::steady_clock::time_point endTime;
    int LowestBitrate;
    std::string browserIp = "";
    std::string chunkName = "";
    std::string serverIp = "";
    double duration = 0.0;
    double throughput = 0.0;
    double avgThroughput = 0.0;
    int bitrate = 0;
    bool chunkRequest = false;
    std::string videoName = "";
};

// Global Variables
const int STATUS_ERROR = -1;
const int MAX_BUFFER_SIZE = 2048;
std::ofstream log_file;

// client/upstream mapping
std::map<int, int> clientToUpstreamMap;

// map used to keep track of what quality and bandwidth are associated with the upstream connection
std::map<int, std::vector<ManifestArgs>> upstreamMap;

// map that is used to track the throughput of the proxy-server connection
std::map<int, double> upstreamThruMap;

// map to keep track of client socket to its ip addr
std::map<int, std::string> ClientToIpMap;
std::map<int, std::string> ServerToIpMap;

// map used to keep track of state for each browser connection by IP
std::map<std::string, ClientState> StateMap;

LogData currLog;

// Send everything to prevent partial send, credit: Beej's Socket programming guide
int sendDataComplete(int s, char *buf, int len)
{
    int total = 0;       // how many bytes we've sent
    int bytesleft = len; // how many we have left to send
    int n;

    while (total < len)
    {
        n = send(s, buf + total, bytesleft, 0);
        if (n == -1)
        {
            break;
        }
        total += n;
        bytesleft -= n;
    }

    return total;
}

void ClearState(const std::string &ipAddress)
{
    StateMap[ipAddress].buf.clear();
    StateMap[ipAddress].totalBytes = 0;
    StateMap[ipAddress].contentLength = 0;
    StateMap[ipAddress].gotHeader = false;
}

// Function to calculate the new throughput
double calculateThru(double currThru, double adap_gain, double newThru)
{
    return adap_gain * newThru + ((1 - adap_gain) * currThru);
}

// gets the content length of the response
void GetContentLength(std::string content, std::string &ipAddress)
{
    std::stringstream ss(content);
    std::string line;
    std::string length = "0";

    //  get the content length in the response
    while (std::getline(ss, line))
    {
        // find the line that contain the quailty info and bandwith associate with each quality
        int pos = line.find("Content-Length:");
        // int headerEndPos = line.find("\r\n\r\n");
        // parse length if header has came through
        if (pos != std::string::npos)
        {
            StateMap[ipAddress].gotHeader = true;
            length = line.substr(pos + 15);
            StateMap[ipAddress].contentLength = std::stoi(length);
            return;
        }
    }
}

// replace the quality of the chunk in the url
std::string modifyURL(std::string &currURL, std::string newQuality)
{
    size_t lastUnderscore = currURL.rfind('_');
    size_t secondLastUnderscore = currURL.rfind('_', lastUnderscore - 1);
    if (lastUnderscore == std::string::npos || secondLastUnderscore == std::string::npos)
    {
        return currURL;
    }

    // Replace the substring between the second last and last underscore with the newQuality
    return currURL.replace(secondLastUnderscore + 1, lastUnderscore - secondLastUnderscore - 1, newQuality);
}

// replace the new url in the message that it should send
void replaceURLInBuffer(char *buffer, size_t &bufferSize, const std::string &oldURL, const std::string &newURL)
{
    // Find the position of the old URL in the buffer
    char *urlPosition = strstr(buffer, oldURL.c_str());
    if (urlPosition == nullptr)
    {
        return; // Return if old URL is not found in the buffer
    }

    // Calculate the positions and lengths
    size_t oldURLLength = oldURL.length();
    size_t newURLLength = newURL.length();
    size_t position = urlPosition - buffer; // Get position of the old URL in the buffer

    // Check if there's enough space in the buffer for the new URL
    if (newURLLength > oldURLLength && (position + newURLLength >= bufferSize))
    {
        std::cerr << "Not enough space in the buffer to replace the old URL with the new URL." << std::endl;
        return; // Handle error if the buffer can't accommodate the new URL
    }

    // If the new URL is shorter or equal in length to the old URL, we can replace it in place
    if (newURLLength <= oldURLLength)
    {
        memcpy(buffer + position, newURL.c_str(), newURLLength);
        if (newURLLength < oldURLLength)
        {
            // If the new URL is shorter, move the remaining part of the buffer to the left
            memmove(buffer + position + newURLLength, buffer + position + oldURLLength, bufferSize - (position + oldURLLength));
        }
    }
    else
    {
        // If the new URL is longer, shift the buffer content to the right to make space
        memmove(buffer + position + newURLLength, buffer + position + oldURLLength, bufferSize - (position + oldURLLength));
        memcpy(buffer + position, newURL.c_str(), newURLLength);
    }

    // Update buffer size accordingly
    bufferSize = bufferSize - oldURLLength + newURLLength;

    // Null-terminate the buffer
    buffer[bufferSize] = '\0';
}

// function to help parse manifest file
void parseManifest(std::string &content, int upstream_fd)
{
    // parse content in the manifest file
    std::stringstream ss(content);
    std::string line;
    int bandwidth = 0;
    std::string qualityName = "";
    int MinBw = INT16_MAX;
    upstreamMap.erase(upstream_fd);

    while (std::getline(ss, line))
    {
        // find the line that contain the quailty info and bandwith associate with each quality
        if (line.rfind("#EXT-X-STREAM-INF", 0) == 0)
        {
            // parse what bandwidth, and name of quality
            int BwPos = line.find("BANDWIDTH=");
            int NamePos = line.find("NAME=");
            if (BwPos != std::string::npos && NamePos != std::string::npos)
            {
                // parse the bandwidth
                std::string bwStr = line.substr(BwPos + 10);
                bandwidth = stof(bwStr) / 1000.0;

                // parse the name of the quality
                size_t nameStart = line.find("NAME=\"", NamePos) + 6;
                size_t nameEnd = line.find('"', nameStart);
                if (nameStart != std::string::npos && nameEnd != std::string::npos)
                {
                    qualityName = line.substr(nameStart, nameEnd - nameStart) + "p";
                }

                // add the bandwidth and quality name for the upstream socket
                ManifestArgs currArg;
                currArg.bandwidth = bandwidth;
                currArg.qualityName = qualityName;
                upstreamMap[upstream_fd].push_back(currArg);

                // set first bitrate as the lowest when first parsing manifest
                if (bandwidth < MinBw)
                {
                    MinBw = bandwidth;
                }
                // currLog.bitrate = MinBw;
                currLog.LowestBitrate = MinBw;
                currLog.avgThroughput = MinBw;
            }
        }
    }
}

// Function to parse the Video chunk url in the Get request
std::string ParseURL(std::string request)
{
    // find the position where video chunk url is located
    size_t getPos = request.find("GET ");
    size_t urlStart = getPos + 5;
    size_t urlEnd = request.find(" HTTP", urlStart);
    std::string directoryUrl = request.substr(urlStart, urlEnd - urlStart);
    size_t firstSlash = directoryUrl.find("/");
    directoryUrl = directoryUrl.substr(firstSlash + 1, urlEnd - firstSlash);

    if (getPos == std::string::npos || urlEnd == std::string::npos)
    {
        return "";
    }

    // Extract the URL substring
    return directoryUrl;
}

// check if this request is requesting a video chunk
bool CheckChunkRequest(std::string request)
{
    if (request.find("GET") != std::string::npos && request.find(".ts") != std::string::npos)
    {
        return true;
    }
    return false;
}

bool isIPAddress(const std::string &input)
{
    struct sockaddr_in sockaddr;
    return inet_pton(AF_INET, input.c_str(), &(sockaddr.sin_addr)) == 1;
}

// Function to parse the command line arguments
void parsingArgument(int argc, char *argv[], Argument &args)
{
    for (int i = 1; i < argc; i++)
    {
        if (strcmp(argv[i], "--proxy-host") == 0)
            args.proxy_host = argv[++i];
        else if (strcmp(argv[i], "--proxy-port") == 0)
            args.proxy_port = atoi(argv[++i]);
        else if (strcmp(argv[i], "--upstream-server-host") == 0)
        {
            // Check if it's ip or host name
            if (isIPAddress(argv[i + 1]))
                args.upstream_host_ip = argv[++i];

            else
                args.upstream_host_name = argv[++i];
        }
        else if (strcmp(argv[i], "--upstream-server-port") == 0)
            args.upstream_port = atoi(argv[++i]);
        else if (strcmp(argv[i], "--adaptation-gain") == 0)
            args.adap_gain = atof(argv[++i]);
        else if (strcmp(argv[i], "--adaptation-bitrate-multiplier") == 0)
            args.adap_multiplier = atof(argv[++i]);
        else if (strcmp(argv[i], "--nameserver-ip") == 0)
            args.nameserver_ip = argv[++i];
        else if (strcmp(argv[i], "--nameserver-port") == 0)
            args.nameserver_port = atoi(argv[++i]);
        else if (strcmp(argv[i], "--log-file-name") == 0)
            args.log_file_name = argv[++i];
    }
}

// Function to create the main socket and set it to non-blocking mode
int CreateMainSocket(const std::string &host, int port)
{
    int mainSocket;
    struct sockaddr_in addr;

    // Create the main socket
    mainSocket = socket(AF_INET, SOCK_STREAM, 0);
    if (mainSocket < 0)
    {
        std::cerr << "Socket creation failed" << std::endl;
        exit(1);
    }

    // Reuse port
    int opt = 1;
    if (setsockopt(mainSocket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0)
    {
        std::cerr << "setsockopt failed" << std::endl;
        exit(1);
    }

    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, host.c_str(), &addr.sin_addr);

    if (bind(mainSocket, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    {
        std::cerr << "Failed to bind the socket on port " << port << std::endl;
        exit(1);
    }

    // Set the socket to listen with a maximum of 1 pending connections
    if (listen(mainSocket, 10) < 0)
    {
        std::cout << "listen error" << std::endl;
        exit(1);
    }

    // std::cout << "Created main " << mainSocket << "Listening on port " << port << std::endl;
    return mainSocket;
}

// Function to connect to the upstream server
int ConnectUpstream(const std::string &host, int port)
{
    int upstreamSocket;
    sockaddr_in server_addr;

    // Create the upstream socket
    upstreamSocket = socket(AF_INET, SOCK_STREAM, 0);
    if (upstreamSocket < 0)
    {
        perror("Upstream socket");
        exit(5);
    }

    struct hostent *host_addr = gethostbyname(host.c_str());
    if (!host_addr)
    {
        std::cout << "host error connet upstream" << std::endl;
        exit(6);
    }

    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(port);

    inet_pton(AF_INET, host.c_str(), &server_addr.sin_addr);
    // try to connect upstrea
    int result = connect(upstreamSocket, (struct sockaddr *)&server_addr, sizeof(server_addr));
    if (result == STATUS_ERROR && errno != EINPROGRESS)
    {
        std::string errorString = "Connection error to upstream server " + host + " on port " + std::to_string(port) + "\n";
        perror(errorString.c_str());
        close(upstreamSocket);
        return STATUS_ERROR;
    }

    // add the server and its ip to the map
    char serverIp[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &server_addr.sin_addr, serverIp, INET_ADDRSTRLEN);
    std::string clientIPStr(serverIp);
    ServerToIpMap[upstreamSocket] = serverIp;

    return upstreamSocket;
}

// handle new connections
int createConnection(int mainSocket, fd_set &mainSet, const Argument &args)
{
    // std::cout << "Entering createConnection()" << std::endl;
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);

    int clientSocket = accept(mainSocket, (struct sockaddr *)&client_addr, &client_len);
    if (clientSocket == STATUS_ERROR)
    {
        perror("Accept Error!");
        exit(4);
    }

    char clientIP[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, clientIP, INET_ADDRSTRLEN);
    std::string clientIPStr(clientIP);

    // Create and connect an upstream socket for this client
    int upstreamSocket = ConnectUpstream(args.upstream_host_ip, args.upstream_port);

    if (upstreamSocket == STATUS_ERROR || upstreamSocket == 0)
    {
        close(clientSocket);
        close(upstreamSocket);
        FD_CLR(clientSocket, &mainSet);
        exit(7);
    }

    FD_SET(clientSocket, &mainSet);
    FD_SET(upstreamSocket, &mainSet);
    // std::cout << "Added client and upstream socket to main set\n";

    clientToUpstreamMap[clientSocket] = upstreamSocket;
    ClientToIpMap[clientSocket] = clientIPStr;
    if (StateMap.find(clientIPStr) == StateMap.end())
    {
        ClientState currState;
        StateMap[clientIPStr] = currState;
        StateMap[clientIPStr].clientSockets.push_back(clientSocket);
    }
    else
    {
        StateMap[clientIPStr].clientSockets.push_back(clientSocket);
    }

    upstreamMap.erase(upstreamSocket);

    return std::max(clientSocket, upstreamSocket);
}

// Function to handle communication
void processConnection(int socket, fd_set &mainSet, double alpha, double multiplier)
{
    char buffer[MAX_BUFFER_SIZE];
    fcntl(socket, F_SETFL, O_NONBLOCK);

    int numReceivedBytes = recv(socket, buffer, sizeof(buffer), 0);

    // nothing is communication, need to close connection
    if (numReceivedBytes == 0)
    {
        // this is a client socket, close corresponding server connection and clear out data
        if (clientToUpstreamMap.find(socket) != clientToUpstreamMap.end())
        {
            std::string ip = ClientToIpMap[socket];
            int upstreamSocket = clientToUpstreamMap[socket];
            close(upstreamSocket);
            FD_CLR(upstreamSocket, &mainSet);
            clientToUpstreamMap.erase(socket);
            ClientToIpMap.erase(socket);
            ServerToIpMap.erase(upstreamSocket);
            upstreamMap.erase(upstreamSocket);
            for (auto it = StateMap[ip].clientSockets.begin(); it != StateMap[ip].clientSockets.end(); ++it)
            {
                if (*it == socket)
                {
                    StateMap[ip].clientSockets.erase(it);
                    break;
                }
            }
        }
        // upstream socket
        else
        {
            int clientSocket = -1;
            // close the corresponding client socket
            for (auto pair : clientToUpstreamMap)
            {
                if (pair.second == socket)
                {
                    clientSocket = pair.first;
                    close(pair.first);
                    FD_CLR(clientSocket, &mainSet);
                    break;
                }
            }

            // clear out the connection in data structure
            std::string ip = ClientToIpMap[clientSocket];
            for (auto it = StateMap[ip].clientSockets.begin(); it != StateMap[ip].clientSockets.end(); ++it)
            {
                if (*it == clientSocket)
                {
                    StateMap[ip].clientSockets.erase(it);
                    break;
                }
            }
            clientToUpstreamMap.erase(clientSocket);
            ClientToIpMap.erase(clientSocket);
            ServerToIpMap.erase(socket);
            upstreamMap.erase(socket);
        }

        close(socket);
        FD_CLR(socket, &mainSet);
        return;
    }
    else if (numReceivedBytes == STATUS_ERROR)
    {
        // Ignore possible linux error
        if (errno == EAGAIN || errno == EWOULDBLOCK)
        {
            return;
        }
    }

    // Handle received bytes
    // Check if data is from client or upstream and forward appropriately
    std::string buffer_str = buffer;
    if (clientToUpstreamMap.find(socket) != clientToUpstreamMap.end())
    {
        // Data received from client, send it to upstream server
        int upstreamSocket = clientToUpstreamMap[socket];
        int dataLen = numReceivedBytes;
        int bytesSent = 0;
        // parse necessary information out of the buffer for a video chunk request
        if (CheckChunkRequest(buffer))
        {
            currLog.chunkRequest = true;
            currLog.chunkName = ParseURL(buffer);
        }
        if (currLog.chunkRequest)
        {
            std::string qualityName = "";
            for (auto args : upstreamMap[upstreamSocket])
            {
                if (currLog.avgThroughput >= (args.bandwidth * multiplier))
                {
                    if (args.bandwidth > currLog.bitrate)
                    {
                        qualityName = args.qualityName;
                        currLog.bitrate = args.bandwidth;
                        size_t bufferSize = strlen(buffer);
                        std::string newUrl = modifyURL(currLog.chunkName, qualityName);
                        currLog.chunkName = newUrl;
                        replaceURLInBuffer(buffer, bufferSize, currLog.chunkName, newUrl);
                    }
                }
            }
        }
        // keep sending request until it has all been sent to the server
        while (bytesSent < dataLen)
        {
            bytesSent += sendDataComplete(upstreamSocket, buffer + bytesSent, dataLen - bytesSent);
            if (bytesSent == STATUS_ERROR)
            {
                std::cout << "Data send error!\n";
                return;
            }
        }
    }
    else
    {
        // Data received from upstream server, find corresponding client and send it
        for (const auto &pair : clientToUpstreamMap)
        {
            if (pair.second == socket)
            {
                std::string ipAddress = ClientToIpMap[pair.first];
                currLog.serverIp = ServerToIpMap[pair.second];
                currLog.browserIp = ipAddress;

                if (strstr(buffer, "#EXTM3U") && strstr(buffer, "BANDWIDTH"))
                {
                    parseManifest(buffer_str, pair.second);
                }

                // only need to parse content len if we have not got the header
                currLog.startTime = std::chrono::steady_clock::now();
                if (strstr(buffer, "\r\n\r\n") != nullptr && !StateMap[ipAddress].gotHeader)
                {
                    GetContentLength(buffer, ipAddress);
                    StateMap[ipAddress].contentLength += strstr(buffer, "\r\n\r\n") - buffer + 4;
                }
                StateMap[ipAddress].totalBytes += numReceivedBytes;
                StateMap[ipAddress].buf.insert(StateMap[ipAddress].buf.end(), buffer, buffer + numReceivedBytes);

                // keep recvieve data until content length and storing it in the State
                while (StateMap[ipAddress].totalBytes < StateMap[ipAddress].contentLength)
                {
                    numReceivedBytes = recv(socket, buffer, sizeof(buffer), 0);
                    buffer_str = buffer;
                    if (strstr(buffer, "#EXTM3U") && strstr(buffer, "BANDWIDTH"))
                    {
                        parseManifest(buffer_str, pair.second);
                    }
                    if (numReceivedBytes < 0)
                    {
                        continue;
                    }

                    StateMap[ipAddress].totalBytes += numReceivedBytes;
                    StateMap[ipAddress].buf.insert(StateMap[ipAddress].buf.end(), buffer, buffer + numReceivedBytes);
                }

                currLog.endTime = std::chrono::steady_clock::now();
                auto durationMs = std::chrono::duration_cast<std::chrono::milliseconds>(currLog.endTime - currLog.startTime).count();
                // currLog.duration = std::max(durationMs / 1000.0, 0.01); // minimum duration to prevent divide by 0 later
                currLog.duration = durationMs / 1000.0;
                if (currLog.duration == 0)
                {
                    currLog.duration = 0.01;
                }
                double currThru = StateMap[ipAddress].totalBytes * 8.0 / currLog.duration / 1000.0;

                currLog.avgThroughput = calculateThru(currLog.avgThroughput, alpha, currThru);
                currLog.throughput = currThru;

                // send completed response to the client, and reset state
                if (StateMap[ipAddress].totalBytes >= StateMap[ipAddress].contentLength && StateMap[ipAddress].contentLength > 0)
                {
                    int bytesSent = 0;
                    while (bytesSent < StateMap[ipAddress].contentLength)
                    {
                        int sendDataLen = StateMap[ipAddress].buf.size();
                        bytesSent += sendDataComplete(StateMap[ipAddress].clientSockets[0], &StateMap[ipAddress].buf[bytesSent], sendDataLen - bytesSent);
                        if (bytesSent < 0)
                        {
                            ClearState(ipAddress);
                            break;
                        }
                    }
                    ClearState(ipAddress);
                }

                // print the log message to the log file for a chunk response
                if (currLog.chunkRequest)
                {
                    log_file << currLog.browserIp << " " << currLog.chunkName << " " << currLog.serverIp << " "
                             << currLog.duration << " " << currLog.throughput << " " << currLog.avgThroughput << " "
                             << currLog.bitrate << std::endl;
                    currLog.chunkRequest = false;
                }
                currLog.bitrate = currLog.LowestBitrate;
            }
        }
    }
}

void resolveHost(Argument &args)
{
    if (args.upstream_host_name.empty())
        return;

    // Create socket for communication with dns
    int resolveSocket = socket(AF_INET, SOCK_DGRAM, 0);
    if (resolveSocket < 0)
    {
        std::cerr << "Resolve socket creation failed" << std::endl;
        exit(1);
    }

    // Prepare request
    sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(args.nameserver_port);
    inet_pton(AF_INET, args.nameserver_ip.c_str(), &serverAddr.sin_addr);
    DNSMessage msg;
    DNSHeader msgHeader;
    msgHeader.ANCOUNT = 0;
    msgHeader.NSCOUNT = 0;
    msgHeader.QR = 0;
    msgHeader.ID = 0;
    msgHeader.QDCOUNT = 1;
    msgHeader.OPCODE = DNSOpcode::QUERY;

    msg.header = msgHeader;
    msg.question.QNAME = DNSDomainName::fromString(args.upstream_host_name);
    msg.question.QTYPE = DNSQType::A;
    msg.question.QCLASS = DNSQClass::IN;
    std::vector<std::byte> serializedData = msg.serialize();
    int status = sendto(resolveSocket, serializedData.data(), serializedData.size(), 0, (struct sockaddr *)&serverAddr, sizeof(serverAddr));

    if (status == STATUS_ERROR)
    {
        close(resolveSocket);
        perror("Send UDP dns Error!");
        exit(1);
    }

    // Prepare receive dns query response
    std::byte buffer[MAX_BUFFER_SIZE];
    socklen_t addrLen = sizeof(serverAddr);
    int numBytesReceived = recvfrom(resolveSocket, buffer, sizeof(buffer), 0, (struct sockaddr *)&serverAddr, &addrLen);
    if (numBytesReceived == STATUS_ERROR)
    {
        close(resolveSocket);
        perror("Receive UDP dns Error!");
        exit(1);
    }

    // Deserialize the data
    try
    {
        DNSMessage responseData = DNSMessage::deserialize(std::span(buffer, numBytesReceived));
        // Loop through answers to find the ip
        for (auto &ans : responseData.answers)
            if (ans.TYPE == DNSRRType::A)
            {
                std::string rawAddrString = std::get<DNSResourceRecord::RecordDataTypes::A>(ans.RDATA).toString();
                // Convert address to string representation

                char addrBuffer[rawAddrString.length() + 1];
                std::strcpy(addrBuffer, rawAddrString.c_str());
                args.upstream_host_ip = addrBuffer;
                break;
            }
    }
    catch (const std::exception &e)
    {
        perror("deseralization error");
        exit(1);
    }
}

int main(int argc, char *argv[])
{
    Argument args;
    parsingArgument(argc, argv, args);
    resolveHost(args);
    // Create the log file for logging
    log_file.open(args.log_file_name);
    if (!log_file.is_open())
    {
        std::cerr << "Log file failed to open" << std::endl;
        return 1;
    }

    // Create the main socket for accepting connections
    int mainSocket = CreateMainSocket(args.proxy_host, args.proxy_port);

    // Create a set for select handling
    fd_set mainSet;
    fd_set readSet;
    fd_set writeSet;
    FD_ZERO(&mainSet);
    FD_ZERO(&readSet);
    FD_ZERO(&writeSet);

    // Add mainSocket to the mainSet
    FD_SET(mainSocket, &mainSet);
    int maxFd = mainSocket;

    // Main loop to handle incoming connections, new or existing
    while (true)
    {
        // Must re-initialize read and write sets since they are modified
        readSet = mainSet;
        writeSet = mainSet;

        // todo first nullptr later is writeset
        int status = select(maxFd + 1, &readSet, &writeSet, nullptr, nullptr);
        if (status == STATUS_ERROR)
        {
            perror("Select Error!");
            exit(3);
        }

        for (int socket = 0; socket <= maxFd; socket++)
        {
            if (FD_ISSET(socket, &readSet))
            {
                // Handle first connection using accept()
                if (socket == mainSocket)
                {
                    int newFd = createConnection(mainSocket, mainSet, args);

                    if (newFd > maxFd)
                        maxFd = newFd;
                }
                else
                {
                    // Handle existing connection
                    processConnection(socket, mainSet, args.adap_gain, args.adap_multiplier);
                }
            }
        }
    }

    // Close all sockets before exiting
    close(mainSocket);
    for (auto &pair : clientToUpstreamMap)
    {
        close(pair.first);  // Close client socket
        close(pair.second); // Close upstream socket
    }
    log_file.close();
    return 0;
}