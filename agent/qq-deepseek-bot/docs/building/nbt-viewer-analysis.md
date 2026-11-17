# Phase 1：NBT Viewer 可复用性分析与验证报告

日期：2026-11-15  
目标版本：Minecraft Java Edition 1.20.1  
上游快照：`misode/vscode-nbt@cc3fdce`、`misode/deepslate@c33b4a6`

## 结论

浏览器 Viewer 可行，但不应整体移植 VS Code 扩展。应直接依赖 `deepslate` 的 NBT、Structure 和 WebGL 渲染 API，并重新实现很薄的浏览器 UI、资源加载和相机控制层。

Phase 1 已建立独立的 Vue 3 + TypeScript 原型：

- 浏览器读取 gzip 或未压缩的 Java Structure NBT；
- 使用 `NbtFile.read` 与 `Structure.fromNbt`；
- 使用 `StructureRenderer` 输出 WebGL 结构和网格；
- 支持鼠标/触摸指针旋转、右键或中键平移、滚轮缩放；
- 固定读取 mcmeta 的 Minecraft 1.20.1 block definitions、models、atlas 与 block properties；
- 支持文件选择和拖放，单文件限制 8 MiB；
- 提供由 Python `nbtlib` 生成的 7×5×7、184 方块测试小屋。

## 上游架构分析

### 可直接复用

| 能力 | 上游模块 | 本原型用法 |
|---|---|---|
| 二进制 NBT 读取 | `deepslate.NbtFile` | `NbtFile.read(Uint8Array)` |
| Java Structure 转换 | `deepslate.Structure` | `Structure.fromNbt(file.root)` |
| BlockState/模型组合 | `BlockDefinition`, `BlockModel` | 从固定 1.20.1 mcmeta JSON 构建 |
| 纹理图集 | `TextureAtlas` | atlas PNG + UV mapping |
| WebGL 几何与绘制 | `StructureRenderer` | 结构、网格、viewport |
| 相机矩阵 | `gl-matrix` | 独立浏览器控制器 |

`deepslate` 官方 README 本身提供 `NbtFile.read` 和 `StructureRenderer` 示例，并明确示例包含鼠标控制与自定义资源包加载：[misode/deepslate](https://github.com/misode/deepslate)。

### 只复用思路、不直接复制

- `StructureEditor.ts`：相机交互和渲染流程值得参考，但它同时包含编辑、方块选择、双 canvas 点击检测、VS Code 消息协议和 UI 状态。本原型只保留相机与 resize 思路。
- `ResourceManager.ts`：资源 provider 的接口组合可复用；原文件依赖扩展构建阶段注入的全局字符串，因此浏览器版改成按 1.20.1 版本显式加载。
- `Schematics.ts`：后续 Sponge/Litematic 格式支持可参考，Phase 1 只实现 Java Structure NBT。

### 不适合浏览器直接复用

- `NbtDocument.ts`、`NbtEditor.ts`、`extension.ts` 强依赖 `vscode.workspace.fs`、Custom Editor、Webview URI、备份与编辑事件。
- `mcmeta.ts`、`Downloader.ts` 使用 Node `fs`、`stream`、`tar` 和服务器缓存目录；浏览器原型应使用静态/CDN 资源，生产版再由后端缓存并同源分发。
- Tree/SNBT/Region 编辑器不属于建筑只读预览范围。

## 数据流

```text
本地 .nbt
  → ArrayBuffer / Uint8Array
  → NbtFile.read
  → Structure.fromNbt
  → 1.20.1 BlockDefinition + BlockModel + TextureAtlas
  → StructureRenderer
  → WebGL canvas
```

这条路径完全不依赖 VS Code API，也不需要 Minecraft Server 或客户端。

## 文件与实现位置

- `building-viewer/src/App.vue`：文件读取、错误与尺寸信息。
- `building-viewer/src/components/StructureCanvas.vue`：WebGL、相机和交互。
- `building-viewer/src/viewer/resources.ts`：固定版本资源 provider。
- `scripts/building/generate_test_structure.py`：NBT fixture 生成及回读断言。
- `building-viewer/public/fixtures/test-house.nbt`：测试结构。
- `building-viewer/LICENSES/MISODE-MIT.txt`：上游许可证与版权声明。

## 验证结果

| 检查 | 结果 |
|---|---|
| Python 生成 NBT | 通过：184 blocks，767 bytes |
| nbtlib 回读 size/blocks | 通过 |
| Vue/TypeScript 类型检查 | 通过 |
| Vite production build | 通过：151 modules，JS gzip 约 95.48 KiB |
| 临时 HTTP 页面 | 200 |
| 临时 HTTP fixture | 200，767 bytes |
| 搜索工具回归测试 | 3 passed |
| 真实公共搜索 | 1.2 秒，5 条结果 |

当前服务器没有 Chromium/Chrome 和 VS Code 图形环境，因此尚未在本机完成真实浏览器像素截图、鼠标事件自动化和 VS Code Viewer 并排视觉对照。这三项是 Phase 1 的人工验收项，不应仅凭编译成功宣称已通过。

## 已知兼容限制

- 仅保证 Minecraft Java 1.20.1 Structure NBT；暂未接入 `.schem`、`.litematic`、旧 `.schematic`、Region 或 Bedrock 格式。
- mcmeta 资源从 GitHub Raw 加载；首次打开受外网与 CORS 影响。Phase 4 应缓存并同源提供资源。
- 透明/半透明、自遮挡标志目前采用精简规则；水、玻璃连接、栅栏连接等复杂状态需要更完整的 block flags。
- 方块实体和特殊动态渲染并非全部支持；箱子、旗帜、告示牌文字、实体、动画纹理可能缺失或近似显示。
- 模组方块没有对应模型/纹理时不能正确显示。上游也记录了未知方块缺失纹理的问题：[vscode-nbt issue #62](https://github.com/misode/vscode-nbt/issues/62)。
- deepslate 已知存在透明混合、水体/活板门裁剪等渲染问题，需在后续兼容测试中建立样本集：[deepslate issues](https://github.com/misode/deepslate/issues)。

## 安全与许可证

- 文件仅在浏览器内解析，Phase 1 没有上传 API。
- 文件大小在读取前限制为 8 MiB；Phase 4 还需增加解压后体积、尺寸、palette 和方块数量限制。
- 未复制 Mojang 纹理到仓库，运行时读取版本化 mcmeta 资源。
- `deepslate` 与 `vscode-nbt` 使用 MIT License；项目保留 Misode 的版权及许可文本。

## Phase 1 剩余人工验收

1. 在支持 WebGL 的桌面浏览器执行 `npm run dev`，确认小屋纹理、旋转、平移、缩放。
2. 用 VS Code NBT Viewer 打开同一 `test-house.nbt`，比较尺寸、palette、门洞、窗户和屋顶。
3. 记录浏览器/GPU/驱动以及视觉差异。

完成人工验收并确认后，才进入 Phase 2；当前没有实现建筑 DSL、Modern Villa、DeepSeek 建筑规划、QQ 工具、任务数据库或上传服务。
