<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { NbtFile, Structure } from 'deepslate'
import StructureCanvas from './components/StructureCanvas.vue'

const structure = shallowRef<Structure | null>(null)
const fileName = ref('test-house.nbt')
const error = ref('')
const loading = ref(false)
const input = ref<HTMLInputElement | null>(null)
const taskId = ref('')
const token = ref('')
const blockCount = ref<number | null>(null)
const history = ref<any[]>([])
const historyOpen = ref(false)
const uploadInput = ref<HTMLInputElement | null>(null)
const imageInput = ref<HTMLInputElement | null>(null)
const pixelMode = ref(false)
const pixelUrl = ref('')
const pageMode = ref(location.pathname === '/oalogin' ? 'admin' : location.pathname === '/dashboard' ? 'dashboard' : location.pathname.startsWith('/gomoku/') ? 'gomoku' : location.pathname === '/' ? 'login' : 'viewer')
const username = ref('')
const adminPassword = ref('')
const sessionName = ref('')
const isAdmin = ref(false)
const dashboardItems = ref<any[]>([])
const formError = ref('')
const game = ref<any>(null)
const gameMessage = ref('')
const gameId = ref(location.pathname.split('/').pop() || '')

async function loadBytes(bytes: ArrayBuffer, name: string) {
  error.value = ''
  loading.value = true
  try {
    if (bytes.byteLength > 8 * 1024 * 1024) throw new Error('NBT 文件不能超过 8 MiB')
    const file = NbtFile.read(new Uint8Array(bytes))
    structure.value = Structure.fromNbt(file.root)
    fileName.value = name
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法解析 NBT 文件'
  } finally {
    loading.value = false
  }
}

async function loadFixture() {
  const response = await fetch('./fixtures/test-house.nbt')
  if (!response.ok) throw new Error(`测试文件加载失败：HTTP ${response.status}`)
  await loadBytes(await response.arrayBuffer(), 'test-house.nbt')
}

async function loadRemote() {
  const match = location.pathname.match(/^\/(b|p)\/([0-9a-f]{32})$/)
  if (!match) return false
  pixelMode.value = match[1] === 'p'
  taskId.value = match[2]
  token.value = new URLSearchParams(location.search).get('token') || ''
  loading.value = true
  let info: any = null
  for (let attempt = 0; attempt < 90; attempt++) {
    const metadata = await fetch(`/api/b/${taskId.value}?token=${encodeURIComponent(token.value)}`)
    const detail = await metadata.json().catch(() => ({}))
    if (!metadata.ok) throw new Error(detail.detail || `访问失败：HTTP ${metadata.status}`)
    info = detail
    if (info.status === 'failed') throw new Error(info.error || '生成失败，未产生可预览文件')
    if (info.status === 'completed') break
    fileName.value = `任务处理中：${info.status}`
    await new Promise(resolve => setTimeout(resolve, 2000))
  }
  if (!info || info.status !== 'completed') throw new Error('生成等待超时，请稍后从历史页面重新打开')
  blockCount.value = info.block_count
  if (pixelMode.value) {
    pixelUrl.value = `/api/b/${taskId.value}/pixel-art?token=${encodeURIComponent(token.value)}`
    fileName.value = `${taskId.value.slice(0, 8)}-pixel-art.png`
    return true
  }
  const response = await fetch(`/api/b/${taskId.value}/download/nbt?token=${encodeURIComponent(token.value)}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `NBT 文件尚未生成或已丢失：HTTP ${response.status}`)
  }
  await loadBytes(await response.arrayBuffer(), `${taskId.value.slice(0, 8)}.nbt`)
  return true
}

function downloadPixel() {
  location.href = `/api/b/${taskId.value}/pixel-art?download=true&token=${encodeURIComponent(token.value)}`
}

function download(kind: 'nbt' | 'schem') {
  location.href = `/api/b/${taskId.value}/download/${kind}?token=${encodeURIComponent(token.value)}`
}

async function showHistory() {
  const response = await fetch(`/api/b/${taskId.value}/history?token=${encodeURIComponent(token.value)}`)
  if (!response.ok) throw new Error(`历史加载失败：HTTP ${response.status}`)
  history.value = (await response.json()).items || []
  historyOpen.value = true
}

async function uploadBuilding(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const body = new FormData(); body.append('file', file)
    const response = await fetch(`/api/b/${taskId.value}/upload?token=${encodeURIComponent(token.value)}`, { method: 'POST', body })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || `上传失败：HTTP ${response.status}`)
    location.href = result.url
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '上传失败' }
}

async function uploadImage(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const body = new FormData(); body.append('file', file)
    const response = await fetch(`/api/b/${taskId.value}/pixel-art?token=${encodeURIComponent(token.value)}`, { method: 'POST', body })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || `图片处理失败：HTTP ${response.status}`)
    location.href = result.url
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '图片上传失败，请检查网络和文件大小' }
}

async function login() {
  formError.value = ''
  const response = await fetch('/api/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username: username.value}) })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '登录失败'; return }
  location.href = result.redirect
}

async function adminLogin() {
  formError.value = ''
  const response = await fetch('/api/admin/login', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({password: adminPassword.value}) })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '认证失败'; return }
  location.href = result.redirect
}

async function loadDashboard() {
  const session = await fetch('/api/session')
  if (!session.ok) { location.href = '/'; return }
  const info = await session.json(); sessionName.value = info.username; isAdmin.value = info.admin
  const historyResponse = await fetch('/api/web/history')
  if (historyResponse.ok) dashboardItems.value = (await historyResponse.json()).items || []
}

async function dashboardUpload(event: Event, pixel: boolean) {
  const file = (event.target as HTMLInputElement).files?.[0]; if (!file) return
  formError.value = ''
  const body = new FormData(); body.append('file', file)
  const response = await fetch(pixel ? '/api/web/pixel-art' : '/api/web/upload', {method:'POST', body})
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '上传失败'; return }
  location.href = result.url
}

async function createGame(mode: 'agent' | 'pvp') {
  formError.value = ''
  const response = await fetch('/api/gomoku', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode})})
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '创建对局失败'; return }
  location.href = result.url
}

async function loadGame() {
  const session = await fetch('/api/session')
  if (!session.ok) { location.href = '/'; return }
  const info = await session.json(); sessionName.value = info.username; isAdmin.value = info.admin
  let response = await fetch(`/api/gomoku/${gameId.value}`)
  if (response.status === 404 && !isAdmin.value) {
    const joined = await fetch(`/api/gomoku/${gameId.value}/join`, {method:'POST'})
    if (joined.ok) response = await fetch(`/api/gomoku/${gameId.value}`)
  }
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '对局加载失败'; return }
  game.value = result
  if (game.value.mode === 'pvp' && game.value.status !== 'finished') setTimeout(loadGame, 2000)
}

async function playCell(x: number, y: number) {
  const response = await fetch(`/api/gomoku/${gameId.value}/move`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({x,y})})
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '落子失败'; return }
  formError.value = ''; game.value = result
}

async function sendGameChat() {
  if (!gameMessage.value.trim()) return
  const response = await fetch(`/api/gomoku/${gameId.value}/chat`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:gameMessage.value})})
  const result = await response.json().catch(() => ({}))
  if (!response.ok) { formError.value = result.detail || '发送失败'; return }
  gameMessage.value = ''; game.value = result
}

async function logout() {
  await fetch('/api/logout', {method:'POST'}); location.href = '/'
}

async function choose(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) await loadBytes(await file.arrayBuffer(), file.name)
}

async function drop(event: DragEvent) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (file) await loadBytes(await file.arrayBuffer(), file.name)
}

const prevent = (event: DragEvent) => event.preventDefault()
onMounted(() => {
  window.addEventListener('dragover', prevent)
  window.addEventListener('drop', prevent)
  if (pageMode.value === 'dashboard') void loadDashboard()
  else if (pageMode.value === 'gomoku') void loadGame()
  else if (pageMode.value === 'viewer') void loadRemote().catch(cause => {
    loading.value = false
    error.value = cause instanceof Error ? cause.message : String(cause)
  })
})
onBeforeUnmount(() => {
  window.removeEventListener('dragover', prevent)
  window.removeEventListener('drop', prevent)
})
</script>

<template>
  <main class="shell" @drop="drop">
    <section v-if="pageMode === 'login'" class="login-card">
      <p class="eyebrow">DAFEIYU CREATIVE STUDIO</p><h1>大肥鱼创作工坊</h1>
      <p>输入用户名进入你的创作空间。首次使用会在当前浏览器认领该名称。</p>
      <input v-model="username" maxlength="24" placeholder="用户名" @keyup.enter="login" />
      <button class="upload" @click="login">进入详情页</button>
      <a class="admin-link" href="/oalogin">主人登录</a>
      <p v-if="formError" class="error">{{ formError }}</p>
    </section>
    <section v-else-if="pageMode === 'admin'" class="login-card">
      <p class="eyebrow">OWNER ACCESS</p><h1>主人认证</h1>
      <input v-model="adminPassword" type="password" placeholder="管理密码" @keyup.enter="adminLogin" />
      <button class="upload" @click="adminLogin">登录</button>
      <a class="admin-link" href="/">返回首页</a>
      <p v-if="formError" class="error">{{ formError }}</p>
    </section>
    <section v-else-if="pageMode === 'dashboard'" class="dashboard">
      <a v-if="isAdmin" class="game-button" href="/companion">大肥鱼拟人管理</a>
      <header><div><p class="eyebrow">CREATIVE DASHBOARD</p><h1>{{ isAdmin ? '全局管理' : sessionName + ' 的创作空间' }}</h1></div><button class="upload" @click="logout">退出</button></header>
      <div class="game-actions"><button class="game-button" @click="createGame('agent')">和大肥鱼下棋</button><button class="game-button" @click="createGame('pvp')">创建双人房间</button><label class="game-button file-button">上传 NBT / Schematic<input hidden type="file" accept=".nbt,.schem,.schematic" @change="dashboardUpload($event,false)"/></label><label class="game-button file-button">上传图片转像素画<input hidden type="file" accept="image/jpeg,image/png,image/webp" @change="dashboardUpload($event,true)"/></label></div>
      <p v-if="formError" class="error">{{ formError }}</p>
      <div class="viewer-card history-card"><div class="status"><strong>{{ isAdmin ? '所有用户历史' : '我的历史' }}</strong><span>{{ dashboardItems.length }} 项</span></div>
        <div class="history-row" v-for="item in dashboardItems" :key="item.task_id"><span>{{ item.web_username || ('QQ '+item.user_id) }}</span><span>{{ item.source === 'image' ? '像素画' : item.source === 'upload' ? '上传' : '生成' }}</span><span :title="item.error">{{ item.status }}{{ item.error ? ' · ' + item.error : '' }}</span><span>{{ item.request }}</span><a :href="item.url">{{ item.task_id.slice(0,8) }}</a></div>
      </div>
    </section>
    <section v-else-if="pageMode === 'gomoku'" class="game-page">
      <header><div><p class="eyebrow">GOMOKU</p><h1>{{ game?.mode === 'agent' ? '和大肥鱼下五子棋' : '双人五子棋' }}</h1></div><a class="upload" href="/dashboard">返回详情页</a></header>
      <p v-if="formError" class="error">{{ formError }}</p>
      <div v-if="game" class="game-layout">
        <div class="board-wrap"><div class="game-meta"><span>黑：{{ game.black }}</span><span>白：{{ game.white || '等待加入' }}</span><span>{{ game.status === 'finished' ? '胜者：'+game.winner : game.status === 'waiting' ? '等待对手打开本页' : '轮到：'+(game.turn === 'X' ? game.black : game.white) }}</span></div>
          <div class="gomoku-board"><template v-for="(row,y) in game.board" :key="y"><button v-for="(cell,x) in row" :key="x" class="gomoku-cell" :class="{last:game.last?.[0]===x&&game.last?.[1]===y}" :title="String.fromCharCode(65+x)+(y+1)" @click="playCell(x,y)"><span v-if="cell !== '.'" :class="cell === 'X' ? 'black-stone' : 'white-stone'"></span></button></template></div>
          <p v-if="game.mode === 'pvp'" class="hint">把当前页面链接发给另一位已登录用户即可加入。</p>
        </div>
        <aside class="game-chat"><h3>和大肥鱼说话</h3><div class="chat-scroll"><div v-for="(item,index) in game.chat" :key="index" :class="['chat-line',item.role]">{{ item.text }}</div></div><div v-if="game.mode === 'agent'" class="chat-input"><input v-model="gameMessage" maxlength="300" placeholder="边下棋边聊点什么…" @keyup.enter="sendGameChat"/><button class="upload" @click="sendGameChat">发送</button></div><p v-else class="hint">双人对局暂不启用 Agent 聊天。</p></aside>
      </div>
    </section>
    <template v-else>
    <header>
      <div><p class="eyebrow">DAFEIYU CREATIVE STUDIO</p><h1>{{ pixelMode ? '马赛克像素画' : 'NBT 建筑预览' }}</h1></div>
      <div><button v-if="taskId && !pixelMode" class="upload" @click="download('nbt')">下载 NBT</button>
      <button v-if="taskId && !pixelMode" class="upload" @click="download('schem')">下载 Schematic</button>
      <button v-if="taskId && pixelMode" class="upload" @click="downloadPixel">下载 PNG</button>
      <button v-if="taskId" class="upload" @click="showHistory">查看历史</button>
      <button v-if="taskId" class="upload" @click="uploadInput?.click()">上传建筑</button>
      <input ref="uploadInput" hidden type="file" accept=".nbt,.schem,.schematic" @change="uploadBuilding" />
      <button v-if="taskId" class="upload" @click="imageInput?.click()">上传图片转像素画</button>
      <input ref="imageInput" hidden type="file" accept="image/jpeg,image/png,image/webp" @change="uploadImage" />
      <button v-if="!pixelMode" class="upload" @click="input?.click()">打开 NBT</button></div>
      <input ref="input" hidden type="file" accept=".nbt" @change="choose" />
    </header>
    <section class="viewer-card">
      <div v-if="pixelMode && pixelUrl" class="pixel-stage"><img :src="pixelUrl" alt="生成的马赛克像素画" /></div>
      <StructureCanvas v-else-if="structure" :structure="structure" />
      <div v-else class="empty">{{ loading ? '正在读取…' : '拖入一个 Structure NBT 文件' }}</div>
      <div class="status">
        <span>{{ fileName }}</span>
        <span v-if="structure && !pixelMode">尺寸 {{ structure.getSize().join(' × ') }}</span>
        <span v-if="blockCount !== null">方块 {{ blockCount }}</span>
        <span v-if="error" class="error">{{ error }}</span>
      </div>
    </section>
    <section v-if="historyOpen" class="viewer-card history-card">
      <div class="status"><strong>生成与上传历史</strong><button class="upload" @click="historyOpen=false">关闭</button></div>
      <div class="history-row" v-for="item in history" :key="item.task_id">
        <span>QQ {{ item.user_id }}</span><span>{{ item.source === 'image' ? '像素画' : item.source === 'upload' ? '上传' : '生成' }}</span>
        <span>{{ item.status }}</span><span>{{ item.request }}</span>
        <a :href="item.url">{{ item.task_id.slice(0, 8) }}</a>
      </div>
      <p class="hint">出于隔离要求，其他历史任务不会共享当前 Token；请从对应 QQ 完成消息中的链接打开。</p>
    </section>
    <p class="hint">{{ pixelMode ? '图片由本机代码处理，最长边不超过 100 像素' : '左键旋转 · 右键或中键平移 · 滚轮缩放 · 支持拖放本地 NBT' }}</p>
    </template>
  </main>
</template>
