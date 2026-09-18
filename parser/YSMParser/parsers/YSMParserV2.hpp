#pragma once
#include "YSMParser.hpp"
#include <utility>
#include <vector>
#include <string>
#include <array>
#include <map>

class YSMParserV2 : public YSMParser {
public:
	YSMParserV2(std::unique_ptr<char[]> buffer, size_t size) : m_buffer(std::move(buffer)) , m_size(size) {}
	~YSMParserV2() = default;
	int getYSGPVersion() override { return 2; };
	std::vector<uint8_t> getDecryptedData() override;
	void saveToDirectory(std::string output_directory) override;
	void parse() override;
private:
	size_t m_size;
	std::unique_ptr<char[]> m_buffer;
	std::vector<uint8_t> m_decryptedData;
	std::array<uint8_t, 16> m_key;
	std::map<std::string, std::vector<uint8_t>> m_resources;
};
