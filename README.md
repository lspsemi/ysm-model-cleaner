# YSM 模型清理工具

用于 Windows 的 Python GUI 工具，支持 YSM 模型批量解包、异常数据检测、垃圾几何清理和默认隐藏处理。

## 功能

- 分析解包后的工程，保存清理副本。
- 使用修改后的 YSMParser 0.3.6，在内部解析时记录 anti-parser 异常数据特征，供 GUI 读取；名称命中仅作为辅助线索。
- 选择目录批量解包，设置日志等级，以及保留或清理检测到的 anti-parser 数据。
- 输出运行日志，并支持保存日志。
- 2.5 档默认隐藏：结合 controller 默认状态、部分条件表达式和投射物配置，生成隐藏动画、烘焙隐藏几何或删除隐藏部件。

用于 Blockbench 编辑时，推荐选择 **2.5档：烘焙编辑器隐藏几何**。该模式清空默认隐藏骨骼及子骨骼的 cubes，保留骨骼和动画引用。仅写入隐藏动画时，Blockbench 编辑模式不会自动应用动画。

2.5 档按站立、空手、静止等默认状态处理，只支持部分表达式，并未完整模拟游戏。烘焙和删除会移除部分几何，处理结果用于编辑副本；保留原始工程，不要直接作为完整游戏模型替换。

## 运行

安装带 Tkinter 的 Python 3.10 或更高版本，然后运行：

```powershell
python ysm_garbage_cleaner_gui.py
```

GUI 无需额外 Python 运行依赖。`YSMParser.exe` 应与 Python 文件或打包后的 GUI EXE 放在同一目录。整理目录附带当前修改版解析器；其 EXE 默认不提交到 Git，可放到 GitHub Releases。

## 打包 Windows EXE

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller ysm_model_cleaner.spec
Copy-Item YSMParser.exe dist/YSMParser.exe
```

分发 `dist` 内的 GUI EXE 和 `YSMParser.exe`，用户双击 GUI 即可使用。

## 编译解析器

安装 CMake 和 Visual Studio 2022 Build Tools（桌面 C++ 工作负载及 Windows SDK）：

```powershell
cmake -S parser -B build/parser -G "Visual Studio 17 2022" -A x64
cmake --build build/parser --config Release --target YSMParser
Copy-Item build/parser/YSMParser/YSMParser.exe YSMParser.exe
```

## 目录

```text
ysm_garbage_cleaner_gui.py   GUI 与模型处理逻辑
ysm_model_cleaner.spec      不含本机绝对路径的打包配置
requirements-build.txt     打包依赖
parser/                    修改后的 YSMParser 0.3.6 源码与第三方依赖
YSMParser.exe              本地解析器，不默认提交
```

## 来源

解析器基于 [OpenYSM/YSMParser](https://github.com/OpenYSM/YSMParser)，保留原始 MIT 许可证于 `parser/LICENSE.txt`，第三方依赖的许可证保留在各自目录。本地修改包括解析诊断输出（`_ysm_parser_diagnostics.json`）及 MSVC UTF-8 编译选项。GUI 的发布许可证尚未指定。

模型与截图不包含在本工程中。请只处理有权使用的模型。
