#pragma once
struct PlayerTextureCollector {
	struct Entry {
		std::string baseName;
		std::vector<std::pair<std::string, std::string>> variants;
		std::unordered_map<std::string, size_t> variantIndex;
	};

	std::vector<Entry> entries;
	std::unordered_map<std::string, size_t> entryIndex;

	static std::pair<std::string, std::string> splitName(const std::string& rawName) {
		size_t slashPos = rawName.find('/');
		if (slashPos == std::string::npos) {
			return { rawName, "uv" };
		}
		return { rawName.substr(0, slashPos), rawName.substr(slashPos + 1) };
	}

	void add(const std::string& rawName, const std::string& path) {
		auto [baseName, type] = splitName(rawName);

		size_t entryPos;
		auto entryIt = entryIndex.find(baseName);
		if (entryIt == entryIndex.end()) {
			entryPos = entries.size();
			entryIndex[baseName] = entryPos;
			entries.push_back(Entry{ baseName, {}, {} });
		}
		else {
			entryPos = entryIt->second;
		}

		Entry& entry = entries[entryPos];
		auto variantIt = entry.variantIndex.find(type);
		if (variantIt == entry.variantIndex.end()) {
			entry.variantIndex[type] = entry.variants.size();
			entry.variants.push_back({ type, path });
		}
		else {
			entry.variants[variantIt->second].second = path;
		}
	}

	void emitTo(nlohmann::ordered_json& playerNode) const {
		if (entries.empty()) return;

		using json = nlohmann::ordered_json;
		playerNode["texture"] = json::array();
		for (const auto& entry : entries) {
			json texObj = json::object();
			for (const auto& variant : entry.variants) {
				texObj[variant.first] = variant.second;
			}
			playerNode["texture"].push_back(texObj);
		}
	}
};