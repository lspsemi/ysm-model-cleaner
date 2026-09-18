#include "YSMParserV2.hpp"
#include <stdexcept>
#include <md5.h>
#include <zlib.h>
#include <base64.h>
#include <algorithm>
#include <AES.h>
#include <string.h>
#include <cstdint>
#include <string>
#include <vector>
#include "YSMParser.hpp"
#include "exceptions/ParserException.hpp"
#include <utility>
#include <filesystem>
#include <fstream>

// ==========================================
// 辅助类与函数：JavaRandom 伪随机数发生器
// ==========================================
class JavaRandom {
private:
    uint64_t seed;
    const uint64_t multiplier = 0x5DEECE66DULL; // 25214903917
    const uint64_t addend = 0xBULL;             // 11
    const uint64_t mask = (1ULL << 48) - 1;     // 281474976710655

public:
    JavaRandom(uint64_t initialSeed) {
        seed = (initialSeed ^ multiplier) & mask;
    }

    int32_t next(int bits) {
        seed = (seed * multiplier + addend) & mask;
        return static_cast<int32_t>(seed >> (48 - bits));
    }

    void nextBytes(std::vector<uint8_t>& bytes) {
        for (size_t i = 0; i < bytes.size(); ) {
            int32_t rnd = next(32);
            for (int n = std::min(bytes.size() - i, (size_t)4); n-- > 0; rnd >>= 8) {
                bytes[i++] = rnd & 0xFF;
            }
        }
    }
};

// ==========================================
// 辅助函数：密码学与压缩操作
// ==========================================

// 计算 MD5
static std::vector<uint8_t> calculateMD5(const std::vector<uint8_t>& data) {
    std::vector<uint8_t> hash(16);
    md5bin(data.data(), data.size(), hash.data());
    return hash;
}

// 模拟 JS 中的 hashToLong (保留后 8 字节作为大端 64 位整型)
static uint64_t hashToLong(const std::vector<uint8_t>& hash) {
    uint64_t result = 0;
    for (size_t i = 8; i < 16; ++i) {
        result = (result << 8) | hash[i];
    }
    return result;
}

// Base64 解码
static std::string base64Decode(const std::string& input) {
    return base64_decode(input);
}

// AES-CBC 解密
static std::vector<uint8_t> aesDecrypt(const std::vector<uint8_t>& key, const std::vector<uint8_t>& iv, const std::vector<uint8_t>& data) {
    AES aes(AESKeyLength::AES_128);
    auto c = aes.DecryptCBC(data, key, iv);
    return c;
}

// Zlib 解压
static std::vector<uint8_t> zlibDecompress(const std::vector<uint8_t>& compressedData) {
    std::vector<uint8_t> decompressed(compressedData.size() * 4); // 预估解压大小
    unsigned long decompressedLen = decompressed.size();

    while (true) {
        int res = uncompress(decompressed.data(), &decompressedLen, compressedData.data(), compressedData.size());
        if (res == Z_BUF_ERROR) {
            decompressed.resize(decompressed.size() * 2);
            decompressedLen = decompressed.size();
        }
        else if (res == Z_OK) {
            decompressed.resize(decompressedLen);
            break;
        }
        else {
            throw std::runtime_error("Zlib decompression failed");
        }
    }
    return decompressed;
}

// ==========================================
// 类方法实现
// ==========================================

std::vector<uint8_t> YSMParserV2::getDecryptedData() {
    return m_decryptedData;
}

void YSMParserV2::saveToDirectory(std::string output_directory)
{
    namespace fs = std::filesystem;

    // 1. 确保输出目录存在
    fs::path dirPath = PathUtils::utf8_to_path(output_directory);
    if (!fs::exists(dirPath)) {
        fs::create_directories(dirPath);
    }

    // 2. 遍历资源 map
    // pair.first 是文件名 (std::string)
    // pair.second 是文件数据 (std::vector<uint8_t>)
    for (const auto& [filename, data] : m_resources) {

        // 拼接完整的输出路径 (例如: output_directory/image.png)
        fs::path filePath = dirPath / PathUtils::utf8_to_path(filename);

        // 需确保资源的父级目录也被创建
        if (filePath.has_parent_path() && !fs::exists(filePath.parent_path())) {
            fs::create_directories(filePath.parent_path());
        }

        // 3. 以二进制模式打开文件流
        std::ofstream outFile(filePath, std::ios::out | std::ios::binary);

        if (outFile.is_open()) {
            // 4. 将 vector 数据写入文件
            // data.data() 返回指向内存起始位置的指针
            // data.size() 返回字节数
            outFile.write(reinterpret_cast<const char*>(data.data()), data.size());
            outFile.close();
        }
        else {
            std::cerr << "Failed to open file for writing: " << PathUtils::path_to_utf8(filePath) << std::endl;
        }
    }
}

void YSMParserV2::parse() {
    using namespace MemoryUtils;
    if (!m_buffer || m_size == 0) return;
    char* ip = m_buffer.get();
    size_t offset = 0;
    // Skip Header [Magic, Version]
    offset += 8;
    
	std::memcpy(m_key.data(), ip + offset, 16);
    offset += 16;

    while (offset < m_size)
    {
        uint32_t strSize = readBE<uint32_t>(ip + offset, 0);
        offset += sizeof(uint32_t);

        std::string b64 = readStr(ip, offset, strSize);
        std::string fileName = base64_decode(b64);
        offset += strSize;

        uint32_t dataLen = readBE<uint32_t>(ip + offset, 0);
        offset += sizeof(uint32_t);

        uint32_t encryptedKeyLength = readBE<uint32_t>(ip + offset, 0);
        offset += sizeof(uint32_t);
        if (encryptedKeyLength != 0x20) throw ParserInvalidFileFormatException();

        std::vector<uint8_t> encryptedKey(m_buffer.get() + offset, ip + offset + encryptedKeyLength);
        offset += encryptedKeyLength;

        std::vector<uint8_t> ivBytes(m_buffer.get() + offset, m_buffer.get() + offset + 16);
        offset += 16;

        std::vector<uint8_t> encryptedData(m_buffer.get() + offset, m_buffer.get() + offset + dataLen);
        offset += dataLen;
        auto md5Digest = calculateMD5(encryptedData);
        JavaRandom jRandom(hashToLong(md5Digest));
        std::vector<uint8_t> randomKey(16, 0);
        jRandom.nextBytes(randomKey);
        auto realKey = aesDecrypt(randomKey, ivBytes, encryptedKey);
        auto decrypted = aesDecrypt(realKey, ivBytes, encryptedData);
        auto decompressed = zlibDecompress(decrypted);
        m_resources.emplace(fileName, std::move(decompressed));
    }
}
