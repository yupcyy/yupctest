# Building Viewer — Phase 1

独立的 Vue 3 + TypeScript 浏览器原型，用 `deepslate` 读取并渲染 Minecraft Java 1.20.1 Structure NBT。

```bash
cd building-viewer
npm install
npm run dev
```

生成测试文件：

```bash
.venv/bin/python scripts/building/generate_test_structure.py
```

原型只负责本地浏览器预览，不包含上传服务、访问 Token、QQ 工具、建筑生成任务或 Minecraft Server。上游 Misode MIT 许可证保存在 `LICENSES/MISODE-MIT.txt`。
