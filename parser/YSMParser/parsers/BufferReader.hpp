#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <cstdio>
#include <cmath>
#include <stdexcept>
#include "exceptions/ParserException.hpp"

struct Vector3D {
	float x, y, z;
	Vector3D operator-(const Vector3D& o) const { return { x - o.x, y - o.y, z - o.z }; }
	Vector3D operator+(const Vector3D& o) const { return { x + o.x, y + o.y, z + o.z }; }
	Vector3D operator*(float s) const { return { x * s, y * s, z * s }; }
	Vector3D operator/(float s) const { return { x / s, y / s, z / s }; }
	Vector3D operator*(const Vector3D& o) const { return { x * o.x, y * o.y, z * o.z }; }

	bool operator==(const Vector3D& o) const { return std::abs(x - o.x) < 1e-4 && std::abs(y - o.y) < 1e-4 && std::abs(z - o.z) < 1e-4; }
	bool operator<(const Vector3D& o) const {
		if (std::abs(x - o.x) >= 1e-4) return x < o.x;
		if (std::abs(y - o.y) >= 1e-4) return y < o.y;
		if (std::abs(z - o.z) >= 1e-4) return z < o.z;
		return false;
	}
};

struct BufferReader {
	const uint8_t* data;
	size_t size;
	size_t offset = 0;
	uint8_t seeByte() {
		if (offset >= size)
		{
			throw ParserIndexOutOfBoundException();
		}
		return data[offset];
	}
	uint8_t readByte() {
		if (offset >= size)
		{
			throw ParserIndexOutOfBoundException();
		}
		return data[offset++];
	}
	uint16_t readWordLE() {
		if (offset + 1 >= size)
		{
			throw ParserIndexOutOfBoundException();
		}
		uint16_t result = 0;
		result |= static_cast<uint16_t>(data[offset]);
		result |= static_cast<uint16_t>(data[offset + 1]) << 8;
		offset += 2;
		return result;
	}

	uint64_t readVarint() {
		uint64_t value = 0;
		uint64_t shift = 0;
		uint8_t byte;

		do {
			byte = readByte();
			value |= (uint64_t(byte & 0x7F) << shift);
			shift += 7;
		} while (byte & 0x80);

		return value;
	}

	Vector3D readVector3D() {
		Vector3D vec{};
		vec.x = readFloat();
		vec.y = readFloat();
		vec.z = readFloat();
		return vec;
	}

	float readFloat() {
		if (offset + 4 > size)
		{
			throw ParserIndexOutOfBoundException();
		}
		float f;
		std::memcpy(&f, &data[offset], 4);
		offset += 4;
		return f;
	}

	uint32_t readDword() {
		if (offset + 4 > size)
		{
			throw ParserIndexOutOfBoundException();
		}
		uint32_t r = (*(uint32_t*)(data + offset));
		offset += 4;
		return r;
	}

	std::string readString() {
		uint32_t len = readVarint();

		if (len == 0) return "";

		if (offset + len > size) {
			throw std::runtime_error("Buffer overflow while reading string");
		}

		std::string s((const char*)&data[offset], len);
		offset += len;
		return s;
	}

	std::vector<uint8_t> readByteSequence() {
		uint32_t len = readVarint();
		printf("len=%i\n", len);
		if (offset + len > size) {
			throw ParserIndexOutOfBoundException();
		}

		if (len == 0) return {};
		std::vector<uint8_t> s(len, 0);
		std::copy(data + offset, data + offset + len, s.begin());
		offset += len;

		printf("Last element: 0x%02X\n", s.back());

		return s;
	}

	std::vector<uint8_t> readBytesExactly(uint64_t len) {
		if (offset + len > size) {
			throw ParserIndexOutOfBoundException();
		}

		if (len == 0) return {};
		std::vector<uint8_t> s(len, 0);
		std::copy(data + offset, data + offset + len, s.begin());
		offset += len;

		printf("Last element: 0x%02X\n", s.back());

		return s;
	}

	bool isEOF() { return offset >= size; }
};
