#pragma once
#include "../YSMParser.hpp"
#include <utility>
#include <vector>
#include <string>
#include <array>
#include <unordered_map>
#include <json.hpp>
struct BufferReader;
class YSMParserV3 : public YSMParser {
	friend void testServerDecrypt();
public:
	YSMParserV3(std::unique_ptr<char[]> buffer, size_t size) : m_buffer(std::move(buffer)), m_size(size) {}
	~YSMParserV3() = default;
	int getYSGPVersion() override { return 3; };
	std::vector<uint8_t> getDecryptedData() override;
	void parse() override;
	void saveToDirectory(std::string output_directory) override;
private:
	void deserialize(const uint8_t* bufferData, size_t size);
	void deserializeLegacyV1(BufferReader& reader);
	void deserializeLegacyV15(BufferReader& reader);
	void deserializeModern(BufferReader& reader);

	std::vector<uint8_t> ParseModels(BufferReader& reader);
	void ParseYSMJson(BufferReader& reader);
	nlohmann::ordered_json buildFilesFromParsedData();
	void ParseLegacyYSMInfo(BufferReader& reader);
	std::vector<uint8_t> ParseAnimations(BufferReader& reader);
	std::vector<uint8_t> ParseSpecialImage(BufferReader& reader);

	// Multi API
	void ParseSoundFiles(BufferReader& reader);
	void ParseFunctionFiles(BufferReader& reader);
	void ParseLanguageFiles(BufferReader& reader);
	std::vector<uint8_t> ParseAnimationControllers(BufferReader& reader);
	void ParseTextureFiles(BufferReader& reader);

	size_t m_size;
	std::unique_ptr<char[]> m_buffer;
	std::string m_header;
	std::array<uint8_t, 32> m_key;
	std::array<uint8_t, 24> m_iv;
	uint64_t m_fileHash;
	std::vector<uint8_t> m_binaryData;

	std::vector<uint8_t> m_decrypted;
	std::vector<uint8_t> m_decompressed;

	int m_format;
	std::unordered_map<std::string, std::string> m_subEntityCategories;

	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_soundFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_functionFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_languageFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_animControllerFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_textureFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_avatarFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_modelFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_animationFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_specialImageFiles;
	std::vector<std::pair<std::string, std::vector<uint8_t>>> m_backgroundFiles;
	std::vector<uint8_t> m_infoJsonFile;
	std::vector<uint8_t> m_ysmJsonFile;

	nlohmann::json m_metadata;
};
