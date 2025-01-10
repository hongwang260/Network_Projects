# Makefile for WTP-base

# Compiler and flags
CXX = g++
CXXFLAGS = -std=c++20 -Wall -g

# Include directories
INCLUDE_DIRS = . ../starter_files
INCLUDES = $(foreach dir,$(INCLUDE_DIRS),-I$(dir))

# Source files
SENDER_SRC = wSender.cpp
RECEIVER_SRC = wReceiver.cpp
PACKET_SRC = packet.h
STARTER_HEADERS = ../starter_files/crc32.h ../starter_files/PacketHeader.h

# Target executables
SENDER_EXEC = wSender
RECEIVER_EXEC = wReceiver

# Object files
SENDER_OBJ = $(SENDER_SRC:.cpp=.o)
RECEIVER_OBJ = $(RECEIVER_SRC:.cpp=.o)

.PHONY: all clean

# Default target
all: $(SENDER_EXEC) $(RECEIVER_EXEC)

# Compile object files
%.o: %.cpp $(PACKET_SRC) $(STARTER_HEADERS)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@

# Link wSender executable
$(SENDER_EXEC): $(SENDER_OBJ)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

# Link wReceiver executable
$(RECEIVER_EXEC): $(RECEIVER_OBJ)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

# Clean up build files
clean:
	rm -f $(SENDER_EXEC) $(RECEIVER_EXEC) $(SENDER_OBJ) $(RECEIVER_OBJ)
