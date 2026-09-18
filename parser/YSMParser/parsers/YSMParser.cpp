#include "YSMParser.hpp"
#include "exceptions/ParserException.hpp"
#include "v3/YSMParserV3.hpp"
#include <memory>
#include <fstream>
#include <utility>
#include "YSMParserV2.hpp"
#include "YSMParserV1.hpp"
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

constexpr uint32_t YSGP_MAGIC = 0x50475359; // "YSGP" in ASCII
std::unique_ptr<YSMParser> YSMParserFactory::Create(const std::string& path)
{
	using namespace MemoryUtils;

	std::ifstream file(PathUtils::utf8_to_path(path), std::ios::binary | std::ios::ate);
	if (!file.is_open()) {
		throw std::runtime_error("Failed to open file, check if path exists and encoding is correct.");
	}
	size_t size = file.tellg();
	file.seekg(0, std::ios::beg);
	auto buffer = std::make_unique<char[]>(size);
	file.read(buffer.get(), size);
	if (size < 8) {
		throw ParserInvalidFileFormatException();
	}

	// Detect File Version
	uint64_t utf8Header = readLE24(buffer.get(), 0);
	uint32_t magic3 = readLE<uint32_t>(buffer.get(), 3);
	if (utf8Header == 0xbfbbef && magic3 == YSGP_MAGIC)
	{
		return std::make_unique<YSMParserV3>(std::move(buffer), size);
	}
	uint32_t magic2 = readLE<uint32_t>(buffer.get(), 0);
	uint32_t crypto2 = readBE<uint32_t>(buffer.get(), 4);
	if (magic2 == YSGP_MAGIC)
	{
		if (crypto2 == 2) return std::make_unique<YSMParserV2>(std::move(buffer), size);
		if (crypto2 == 1) return std::make_unique<YSMParserV1>(std::move(buffer), size);
	}
	throw ParserUnSupportVersionException();
}

std::unique_ptr<YSMParser> YSMParserFactory::Create(const char* data, size_t size)
{
	using namespace MemoryUtils;

	if (size < 8) {
		throw ParserInvalidFileFormatException();
	}

	auto buffer = std::make_unique<char[]>(size);
	std::memcpy(buffer.get(), data, size);

	uint64_t utf8Header = readLE24(buffer.get(), 0);
	uint32_t magic3 = readLE<uint32_t>(buffer.get(), 3);
	if (utf8Header == 0xbfbbef && magic3 == YSGP_MAGIC)
	{
		return std::make_unique<YSMParserV3>(std::move(buffer), size);
	}
	uint32_t magic2 = readLE<uint32_t>(buffer.get(), 0);
	uint32_t crypto2 = readBE<uint32_t>(buffer.get(), 4);
	if (magic2 == YSGP_MAGIC)
	{
		if (crypto2 == 2) return std::make_unique<YSMParserV2>(std::move(buffer), size);
		if (crypto2 == 1) return std::make_unique<YSMParserV1>(std::move(buffer), size);
	}
	throw ParserUnSupportVersionException();
}
