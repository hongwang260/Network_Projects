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
#include <queue>
#include "DNS/DNSMessage.h"

class Argument
{
public:
    int port = 0;
    std::string ip_addr = "";
    std::string domain_name = "";
    std::string log_file_name = "nameserver_log.txt";
    std::string round_robin_file_name = "";
    std::string topology_file_name = "";
};

class LogData 
{
public:
    std::string clientIP = "";
    std::string queryName = "";
    std::string responseIP = "";
};

struct Node {
    std::string ip;
    std::string type;
};

// Function to parse the command line arguments
void parsingArgument(int argc, char *argv[], Argument &args)
{
    for (int i = 1; i < argc; i++)
    {
        if (strcmp(argv[i], "--ip") == 0)
            args.ip_addr = argv[++i];
        else if (strcmp(argv[i], "--port") == 0)
            args.port = atoi(argv[++i]);
        else if (strcmp(argv[i], "--domain") == 0)
            args.domain_name = argv[++i];
        else if (strcmp(argv[i], "--log-file-name") == 0)
            args.log_file_name = argv[++i];
        else if (strcmp(argv[i], "--round-robin-ip-list-file-path") == 0)
            args.round_robin_file_name = argv[++i];
        else if (strcmp(argv[i], "--network-topology-file-path") == 0)
            args.topology_file_name = argv[++i];
    }
}

// load all the IPs in the RR file
void loadRRFile(std::string fileDir, std::vector<std::string> &IPs) 
{
    std::ifstream file(fileDir);
    std::string line;
    while (std::getline(file, line)) {
        IPs.push_back(line);
    }
    file.close();
}

// load and parse the topology file into links and nodes
void loadTopology(std::string fileDir, std::map<int, Node> &nodes, std::map<std::pair<int, int>, int> &links) 
{
    int numNodes, numLinks;
    std::ifstream file(fileDir);
    std::string line;
    
    // read all the nodes
    file >> line >> numNodes;
    for (int i = 0; i < numNodes; i++) {
        int nodeId;
        std::string type, ip;
        file >> nodeId >> type >> ip;
        nodes[nodeId] = {ip, type};
    }

    // read all the links 
    file >> line >> numLinks;
    for (int i = 0; i < numLinks; i++) {
        int start, dest, cost;
        file >> start >> dest >> cost;
        links[{start, dest}] = cost;
        links[{dest, start}] = cost;
    }
}

//start the DNS server with UDP
int startDNS(std::string ip, int port) 
{
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    int opt = 1;
    if (setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        perror("Reuse error");
        close(sockfd);
        exit(1);
    }
    if (sockfd < 0) {
        perror("Open error");
        exit(1);
    }

    sockaddr_in serverAddr{};
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_addr.s_addr = inet_addr(ip.c_str());
    serverAddr.sin_port = htons(port);

    // Bind the socket
    if (bind(sockfd, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) < 0) {
        perror("Bind error");
        close(sockfd);
        exit(1);
    }

    return sockfd;

}

// find the closest server node to this client node
Node findClosestServer(int clientNodeId, const std::map<int, Node> &nodes, const std::map<std::pair<int, int>, int> &links) {
    std::map<int, int> distances;
    std::priority_queue<std::pair<int, int>, std::vector<std::pair<int, int>>, std::greater<>> pq;

    for (const auto &node : nodes) {
        distances[node.first] = std::numeric_limits<int>::max();
    }

    distances[clientNodeId] = 0;
    pq.push({0, clientNodeId});

    while (!pq.empty()) {
        auto [dist, nodeId] = pq.top();
        pq.pop();

        if (dist > distances[nodeId]) continue;

        for (const auto &link : links) {
            if (link.first.first == nodeId) {
                int neighbor = link.first.second;
                int newDist = dist + link.second;

                if (newDist < distances[neighbor]) {
                    distances[neighbor] = newDist;
                    pq.push({newDist, neighbor});
                }
            }
        }
    }

    // Find the closest server
    Node closestServer = Node();
    int minDistance = std::numeric_limits<int>::max();
    for (const auto &node : nodes) {
        if (node.second.type == "SERVER" && distances[node.first] < minDistance) {
            minDistance = distances[node.first];
            closestServer = node.second;
        }
    }

    return closestServer;
}

//get the next ip from the RR file and update index 
std::string getNextRoundRobinIP(std::vector<std::string> &ipList, int &index) {
    if (ipList.empty()) return "";
    std::string ip = ipList[index];
    index = (index + 1) % ipList.size();
    return ip;
}

// global variables to keep track of data
std::ofstream logFile;
LogData currLogData;

int main(int argc, char *argv[]) {
    Argument args;
    parsingArgument(argc, argv, args);

    //open log file for logging
    logFile.open(args.log_file_name);
    if (!logFile.is_open())
    {
        std::cerr << "Log file failed to open" << std::endl;
        return 1;
    }

    // start the DNS server
    int socket = startDNS(args.ip_addr, args.port);

    std::vector<std::string> RoundRobinIPs;
    int index = 0;
    std::map<int, Node> nodes;
    std::map<std::pair<int, int>, int> links;
    // check to use RR or Geological and load the corresponding files
    //Case 1: run with RR mode
    if (args.round_robin_file_name != "" && args.topology_file_name == "") 
    {
        loadRRFile(args.round_robin_file_name, RoundRobinIPs);
        while (true) 
        {
            struct sockaddr_in client_addr{};
            socklen_t client_addr_len = sizeof(client_addr);
            std::byte buffer[1024];
            client_addr_len = sizeof(client_addr);
            int msgLen = recvfrom(socket, buffer, sizeof(buffer), 0, (struct sockaddr*)&client_addr, &client_addr_len);

            DNSMessage queryMessage;

            if (msgLen > 0)
            {
                char client_ip[INET_ADDRSTRLEN]; // Buffer for the IP address
                inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, sizeof(client_ip));
                currLogData.clientIP = client_ip;

                try {
                    queryMessage = DNSMessage::deserialize(std::span(buffer, msgLen));
                } catch (const std::exception& e) {
                    perror("deseralization error");
                    continue;
                }

                currLogData.queryName = queryMessage.question.QNAME.toString();
                currLogData.queryName.pop_back();

                // check if domain name is valid
                if (currLogData.queryName == args.domain_name) 
                {
                    std::string serverIP = getNextRoundRobinIP(RoundRobinIPs, index);
                    currLogData.responseIP = serverIP;
                    DNSMessage responseMessage = queryMessage;
                    responseMessage.header.QR = 1;

                    DNSResourceRecord answer;
                    answer.NAME = queryMessage.question.QNAME;
                    answer.TYPE = DNSRRType::A;
                    answer.CLASS = DNSRRClass::IN;
                    answer.TTL = 0;

                    answer.RDLENGTH = 4;
                    answer.RDATA = DNSResourceRecord::RecordDataTypes::A(serverIP);
                    responseMessage.answers.push_back(answer);
                    responseMessage.header.ANCOUNT = responseMessage.answers.size();
                    auto serializedResponse = responseMessage.serialize();
                    sendto(socket, serializedResponse.data(), serializedResponse.size(), 0, (struct sockaddr*)&client_addr, client_addr_len);

                    // logging into the log file
                    logFile << currLogData.clientIP << " " << currLogData.queryName << " " << currLogData.responseIP << std::endl;
                }
                else 
                {   
                    DNSMessage responseMessage = queryMessage;
                    responseMessage.header.QR = 1;
                    responseMessage.header.RCODE = DNSRcode::NAME_ERROR;
                    auto serializedResponse = responseMessage.serialize();
                    sendto(socket, serializedResponse.data(), serializedResponse.size(), 0, (struct sockaddr*)&client_addr, client_addr_len);
                }

            }
        }

    } 
    // Case 2: run with geolocation mode
    else if (args.topology_file_name != "" && args.round_robin_file_name == "") 
    {
        loadTopology(args.topology_file_name, nodes, links);

        while (true) 
        {
            struct sockaddr_in client_addr{};
            socklen_t client_addr_len = sizeof(client_addr);
            std::byte buffer[1024];
            client_addr_len = sizeof(client_addr);
            int msgLen = recvfrom(socket, buffer, sizeof(buffer), 0, (struct sockaddr*)&client_addr, &client_addr_len);

            DNSMessage queryMessage;

            if (msgLen > 0) {
                char client_ip[INET_ADDRSTRLEN]; // Buffer for the IP address
                inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, sizeof(client_ip));
                currLogData.clientIP = client_ip;

                try {
                    queryMessage = DNSMessage::deserialize(std::span(buffer, msgLen));
                } catch (const std::exception& e) {
                    perror("deseralization error");
                    continue;
                }

                currLogData.queryName = queryMessage.question.QNAME.toString();
                currLogData.queryName.pop_back();

                // find the node in the map for this client
                Node clientNode;
                int nodeId = -1;
                for (auto node : nodes) 
                {
                    if (node.second.type == "CLIENT" && node.second.ip == currLogData.clientIP) 
                    {
                        clientNode = node.second;
                        nodeId = node.first;
                    }
                }

                Node closestServer = findClosestServer(nodeId, nodes, links);

                // server is found and it can send 
                if (closestServer.type != "" && args.domain_name == currLogData.queryName)
                {
                    currLogData.responseIP = closestServer.ip;
                    DNSMessage responseMessage = queryMessage;
                    responseMessage.header.QR = 1;

                    DNSResourceRecord answer;
                    answer.NAME = queryMessage.question.QNAME;
                    answer.TYPE = DNSRRType::A;
                    answer.CLASS = DNSRRClass::IN;
                    answer.TTL = 0;

                    answer.RDLENGTH = 4;
                    answer.RDATA = DNSResourceRecord::RecordDataTypes::A(currLogData.responseIP);
                    responseMessage.answers.push_back(answer);
                    responseMessage.header.ANCOUNT = responseMessage.answers.size();
                    auto serializedResponse = responseMessage.serialize();
                    sendto(socket, serializedResponse.data(), serializedResponse.size(), 0, (struct sockaddr*)&client_addr, client_addr_len);

                    // logging into the log file
                    logFile << currLogData.clientIP << " " << currLogData.queryName << " " << currLogData.responseIP << std::endl;
                }
                // server was not found or domain name did not match
                else
                {
                    if (args.domain_name != currLogData.queryName) 
                    {
                        queryMessage.header.QR = 1;
                        queryMessage.header.RCODE = DNSRcode::NAME_ERROR;
                        queryMessage.answers.clear();
                        queryMessage.header.ANCOUNT = 0;
                        queryMessage.header.NSCOUNT = 0;
                        queryMessage.header.ARCOUNT = 0;
                        auto serializedResponse = queryMessage.serialize();
                        sendto(socket, serializedResponse.data(), serializedResponse.size(), 0, (struct sockaddr*)&client_addr, client_addr_len);
                        logFile << currLogData.clientIP << " " << currLogData.queryName << " " << currLogData.responseIP << std::endl;
                    }
                    // wasn't able to find a server for this client
                    else if (closestServer.type == "")
                    {
                        queryMessage.header.QR = 1;
                        queryMessage.header.RCODE = DNSRcode::NO_ERROR;
                        auto serializedResponse = queryMessage.serialize();
                        sendto(socket, serializedResponse.data(), serializedResponse.size(), 0, (struct sockaddr*)&client_addr, client_addr_len);
                    }
                }
            }
        }
    }

    logFile.close();
    //close(socket);

    return 0;
}
