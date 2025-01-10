#include <PacketHeader.h>

struct Packet
{
    PacketHeader header;
    char payload[1456];
};