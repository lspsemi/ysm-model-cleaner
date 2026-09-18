#pragma once
#include <unordered_map>
#include <string>
#include <algorithm>
#include <json.hpp>
#include "PlayerTextureCollector.hpp"

enum class ParseContext {
	Global,
	Player,
	Projectile,
	Vehicle
};

// 辅助函数：去除字符串首尾的空白字符（包括空格、制表符、换行符）
static std::string trim(const std::string& str) {
	size_t first = str.find_first_not_of(" \t\r\n");
	if (first == std::string::npos) return "";
	size_t last = str.find_last_not_of(" \t\r\n");
	return str.substr(first, (last - first + 1));
}

class YSGPHeaderParser {
public:
	int formatVersion = -1;
	std::unordered_map<std::string, std::pair<std::string, std::vector<std::string>>> fileMap;
	nlohmann::ordered_json filesJson;

	void parse(const std::string& headerData) {
		using json = nlohmann::ordered_json;
		filesJson = json::object();
		std::istringstream stream(headerData);
		std::string line;

		ParseContext context = ParseContext::Global;
		std::string contextName = "";
		PlayerTextureCollector playerTextures;

		auto addFileMap = [&](const std::string& hash, const std::string& tag, const std::string& path) {
			fileMap[hash].first = tag;
			fileMap[hash].second.push_back(path);
			};

		auto handleNameAndHash = [&](const std::string& prefix, std::string& out_name, std::string& out_hash) {
			if (line.find(prefix) == 0) {
				std::string content = trim(line.substr(prefix.length()));
				if (content.length() > 64) {
					out_hash = content.substr(content.length() - 64);
					out_name = trim(content.substr(0, content.length() - 64));
					return true;
				}
			}
			return false;
			};

		auto endsWith = [](const std::string& v, const std::string& suffix) {
			if (v.size() < suffix.size()) return false;
			return v.compare(v.size() - suffix.size(), suffix.size(), suffix) == 0;
			};

		auto splitPayload = [&](const std::string& payload, std::string& out_name, std::string& out_hash) {
			if (payload.size() < 64) return false;
			out_hash = payload.substr(payload.size() - 64);
			out_name = trim(payload.substr(0, payload.size() - 64));
			return true;
			};

		auto getLegacyRole = [](std::string_view raw, std::string_view suffix) -> std::string {
			return std::string(raw.substr(0, raw.size() - suffix.size()));
			};

		while (std::getline(stream, line)) {
			line = trim(line);
			if (line.empty()) continue;

			std::string_view sv(line);

			if (sv.starts_with("<format>")) {
				try { formatVersion = std::stoi(std::string(trim(std::string(sv.substr(8))))); }
				catch (...) { throw std::runtime_error("failed to parse <format>"); }
				context = ParseContext::Global;
				continue;
			}

			if (sv.starts_with("<player-model>")) {
				context = ParseContext::Player; contextName = "";
				if (!filesJson.contains("player")) filesJson["player"] = json::object();
				continue;
			}
			if (sv.starts_with("<projectile-model>")) {
				context = ParseContext::Projectile; contextName = trim(std::string(sv.substr(18)));
				if (!filesJson.contains("projectiles")) filesJson["projectiles"] = json::object();
				if (!filesJson["projectiles"].contains(contextName)) filesJson["projectiles"][contextName] = json::object();
				continue;
			}
			if (sv.starts_with("<vehicle-model>")) {
				context = ParseContext::Vehicle; contextName = trim(std::string(sv.substr(15)));
				if (!filesJson.contains("vehicles")) filesJson["vehicles"] = json::object();
				if (!filesJson["vehicles"].contains(contextName)) filesJson["vehicles"][contextName] = json::object();
				continue;
			}
			if (sv.starts_with("<sound>") || sv.starts_with("<language>") ||
				sv.starts_with("<crypto>") || sv.starts_with("<rand>") || sv.starts_with("<time>")) {
				context = ParseContext::Global;
			}

			// 统一处理兼容/遗留后缀
			size_t tagClosePos = sv.find('>');
			if (tagClosePos != std::string_view::npos && sv[0] == '<') {
				std::string_view rawTag = sv.substr(1, tagClosePos - 1);
				std::string payload = trim(std::string(sv.substr(tagClosePos + 1)));
				std::string legacyName, legacyHash;

				if (rawTag.ends_with("-animation-controller") && splitPayload(payload, legacyName, legacyHash)) {
					std::string path = getLegacyRole(rawTag, "-animation-controller");
					if (!path.ends_with(".json")) path += ".json";
					if (!path.starts_with("controller/")) path = "controller/" + path;

					addFileMap(legacyHash, "<animation-controller>", path);
					filesJson["player"]["animation_controllers"].push_back(path);
					continue;
				}

				if (rawTag.ends_with("-model") && splitPayload(payload, legacyName, legacyHash)) {
					std::string role = getLegacyRole(rawTag, "-model");
					std::string path = "models/" + role + ".json";
					addFileMap(legacyHash, "<model>", path);
					if (role == "main" || role == "arm") filesJson["player"]["model"][role] = path;
					else filesJson["projectiles"][role]["model"] = path;
					continue;
				}

				if (rawTag.ends_with("-animation") && splitPayload(payload, legacyName, legacyHash)) {
					std::string role = getLegacyRole(rawTag, "-animation");
					std::string animFile = (role == "fp_arm") ? "fp.arm" :
						(role == "immersive_melodies") ? "im" :
						(role == "irons_spell_books") ? "iss" : role;
					std::string path = "animations/" + animFile + ".animation.json";
					addFileMap(legacyHash, "<animation>", path);
					if (role == "arrow") filesJson["projectiles"]["arrow"]["animation"] = path;
					else filesJson["player"]["animation"][role] = path;
					continue;
				}

				if (rawTag.ends_with("-texture") && splitPayload(payload, legacyName, legacyHash)) {
					std::string role = getLegacyRole(rawTag, "-texture");
					std::string safeRole = role;
					std::replace(safeRole.begin(), safeRole.end(), ':', '_');
					std::string path = "textures/" + safeRole + ".png";
					addFileMap(legacyHash, "<texture>", path);
					if (role == "arrow") filesJson["projectiles"]["arrow"]["texture"] = path;
					else playerTextures.add(role, path);
					continue;
				}

				if (formatVersion <= 4 && rawTag.ends_with(".png") && !payload.empty()) {
					std::string role = std::string(rawTag.substr(0, rawTag.size() - 4));
					std::string safeRole = role;
					std::replace(safeRole.begin(), safeRole.end(), ':', '_');
					std::string path = "textures/" + safeRole + ".png";
					addFileMap(payload, "<texture>", path);
					if (role == "arrow") filesJson["projectiles"]["arrow"]["texture"] = path;
					else playerTextures.add(role, path);
					continue;
				}
			}

			if (context == ParseContext::Projectile || context == ParseContext::Vehicle) {
				std::string group = (context == ParseContext::Projectile) ? "projectiles" : "vehicles";
				auto& targetNode = filesJson[group][contextName];
				
				// 替换组件名称中的非法字符 ':'，以免 Windows 下出现 ADS 符号路径错误
				std::string safeContextName = contextName;
				std::replace(safeContextName.begin(), safeContextName.end(), ':', '_');

				if (sv.starts_with("<model>")) {
					std::string hash = trim(std::string(sv.substr(7)));
					std::string path = "models/" + safeContextName + ".json";
					addFileMap(hash, "<model>", path);
					targetNode["model"] = path;
				}
				else if (sv.starts_with("<animation>")) {
					std::string hash = trim(std::string(sv.substr(11)));
					std::string path = (context == ParseContext::Vehicle)
						? "animations/vehicle/" + safeContextName + ".animation.json"
						: "animations/" + safeContextName + ".animation.json";
					addFileMap(hash, "<animation>", path);
					targetNode["animation"] = path;
				}
				else if (sv.starts_with("<texture>")) {
					std::string content = trim(std::string(sv.substr(9)));
					std::string hash, name;
					if (splitPayload(content, name, hash)) {
						if (!name.empty()) {
							std::string safeName = name;
							std::replace(safeName.begin(), safeName.end(), ':', '_');
							std::string path = "textures/" + safeContextName + "_" + safeName + ".png";
							addFileMap(hash, "<texture>", path);
							if (!targetNode.contains("texture")) targetNode["texture"] = json::object();
							else if (targetNode["texture"].is_string()) {
								targetNode["texture"] = { {"uv", targetNode["texture"]} };
							}
							targetNode["texture"][name] = path;
						}
						else {
							std::string path = "textures/" + safeContextName + ".png";
							addFileMap(hash, "<texture>", path);
							if (!targetNode.contains("texture") || !targetNode["texture"].is_object()) {
								targetNode["texture"] = path;
							}
							else {
								targetNode["texture"]["uv"] = path;
							}
						}
					}
				}
				continue;
			}

			// Player / Global mapping tables
			auto& playerNode = filesJson["player"];
			static const std::vector<std::pair<std::string, std::string>> playerModels = {
				{"<model-main>", "main"}, {"<model-arm>", "arm"},
				{"<main-model>", "main"}, {"<arm-model>", "arm"}
			};

			bool matchedModel = false;
			for (const auto& mod : playerModels) {
				if (sv.starts_with(mod.first)) {
					std::string hash = trim(std::string(sv.substr(mod.first.length())));
					std::string path = "models/" + mod.second + ".json";
					addFileMap(hash, mod.first, path);
					playerNode["model"][mod.second] = path;
					matchedModel = true;
					break;
				}
			}
			if (matchedModel) continue;

			static const std::vector<std::pair<std::string, std::pair<std::string, std::string>>> playerAnims = {
				{"<animation-main>",               {"main",               "main"}},
				{"<animation-arm>",                {"arm",                "arm"}},
				{"<animation-extra>",              {"extra",              "extra"}},
				{"<animation-tac>",                {"tac",                "tac"}},
				{"<animation-carryon>",            {"carryon",            "carryon"}},
				{"<animation-parcool>",            {"parcool",            "parcool"}},
				{"<animation-swem>",               {"swem",               "swem"}},
				{"<animation-fp_arm>",             {"fp_arm",             "fp.arm"}},
				{"<animation-tlm>",                {"tlm",                "tlm"}},
				{"<animation-slashblade>",         {"slashblade",         "slashblade"}},
				{"<animation-immersive_melodies>", {"immersive_melodies", "im"}},
				{"<animation-irons_spell_books>",  {"irons_spell_books",  "iss"}},
				{"<main-animation>",               {"main",               "main"}},
				{"<arm-animation>",                {"arm",                "arm"}},
				{"<extra-animation>",              {"extra",              "extra"}},
				{"<tac-animation>",                {"tac",                "tac"}},
				{"<carryon-animation>",            {"carryon",            "carryon"}},
				{"<parcool-animation>",            {"parcool",            "parcool"}},
				{"<swem-animation>",               {"swem",               "swem"}},
				{"<fp_arm-animation>",             {"fp_arm",             "fp.arm"}},
				{"<tlm-animation>",                {"tlm",                "tlm"}},
				{"<slashblade-animation>",         {"slashblade",         "slashblade"}},
				{"<immersive_melodies-animation>", {"immersive_melodies", "im"}},
				{"<irons_spell_books-animation>",  {"irons_spell_books",  "iss"}}
			};

			bool matchedAnim = false;
			for (const auto& anim : playerAnims) {
				if (sv.starts_with(anim.first)) {
					std::string hash = trim(std::string(sv.substr(anim.first.length())));
					std::string path = "animations/" + anim.second.second + ".animation.json";
					addFileMap(hash, anim.first, path);
					playerNode["animation"][anim.second.first] = path;
					matchedAnim = true;
					break;
				}
			}
			if (matchedAnim) continue;

			// 处理通用前缀属性 (替代冗长的硬编码匹配)
			auto extractMap = [&](std::string_view prefix, std::string_view targetTag, const std::string& pathTemplate) {
				if (!sv.starts_with(prefix)) return false;
				std::string name, hash;
				if (handleNameAndHash(std::string(prefix), name, hash)) {
					// 根据 %s 替换名字映射路径
					std::string path = pathTemplate;
					size_t pos = path.find("%s");
					if (pos != std::string::npos) {
						std::string safeName = name;
						std::replace(safeName.begin(), safeName.end(), ':', '_');
						path.replace(pos, 2, safeName);
					}
					addFileMap(hash, std::string(targetTag), path);
					return true;
				}
				return false;
				};

			if (sv.starts_with("<hash>")) {
				std::string metadataPath = (formatVersion <= 4) ? "info.json" : "ysm.json";
				addFileMap(trim(std::string(sv.substr(6))), "<hash>", metadataPath);
			}
			else if (extractMap("<animation-controller>", "<animation-controller>", "controller/%s.json")) {
				std::string name, hash; handleNameAndHash("<animation-controller>", name, hash);
				std::string safeName = name;
				std::replace(safeName.begin(), safeName.end(), ':', '_');
				filesJson["player"]["animation_controllers"].push_back("controller/" + safeName + ".json");
			}
			else if (extractMap("<texture>", "<texture>", "textures/%s.png")) {
				std::string name, hash; handleNameAndHash("<texture>", name, hash);
				std::string safeName = name;
				std::replace(safeName.begin(), safeName.end(), ':', '_');
				playerTextures.add(name, "textures/" + safeName + ".png");
			}
			else if (extractMap("<sound>", "<sound>", "sounds/%s.ogg")) {}
			else if (extractMap("<language>", "<language>", "lang/%s.json")) {}
		}

		playerTextures.emitTo(filesJson["player"]);
	}
};
